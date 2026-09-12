from __future__ import annotations

import json
import math
import os
import re
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.core.storage import PrivateFileSystemStorage
from apps.documents.models import (
    ImmutableTemplateVersionError,
    InvalidTemplateLifecycleTransition,
    TemplateVersion,
)
from apps.documents.storage_keys import (
    build_template_storage_key,
    sanitize_template_display_filename,
)


def template_values(*, uploader: User, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "type_key": "synthetic-platform-test",
        "version": "v1.0",
        "original_filename": "synthetic-template.docx",
        "checksum_sha256": "a" * 64,
        "byte_size": 1024,
        "status": TemplateVersion.Status.UPLOADED,
        "validation_report": {},
        "uploader": uploader,
        "approval_reference": "SYNTHETIC-APPROVAL-001",
    }
    values.update(overrides)
    return values


def database_bulk_create(templates: list[TemplateVersion]) -> None:
    """Bypass application guards only to exercise database constraints."""
    models.QuerySet.bulk_create(TemplateVersion.objects.all(), templates)


@pytest.mark.django_db
def test_template_version_defaults_to_server_owned_private_identity(
    user_factory: Callable[..., User],
) -> None:
    template = TemplateVersion(**template_values(uploader=user_factory()))

    template.full_clean()
    template.save()

    assert re.fullmatch(
        r"templates/synthetic-platform-test/v1\.0/[0-9a-f]{32}\.docx",
        template.storage_key,
    )
    assert template.storage_key != template.original_filename
    assert template.activated_by is None
    assert template.activated_at is None


def test_storage_key_builder_accepts_no_request_path_and_is_opaque() -> None:
    first = build_template_storage_key("synthetic-platform-test", "v1.0")
    second = build_template_storage_key("synthetic-platform-test", "v1.0")

    assert first != second
    assert re.fullmatch(r"templates/synthetic-platform-test/v1\.0/[0-9a-f]{32}\.docx", first)
    with pytest.raises(ValueError):
        build_template_storage_key("../../request", "v1.0")
    with pytest.raises(ValueError):
        build_template_storage_key("synthetic-platform-test", "../../request")


@pytest.mark.parametrize(
    ("unsafe", "safe"),
    [
        ("../../unsafe.docx", "unsafe.docx"),
        (r"C:\\private\\unsafe.docx", "unsafe.docx"),
        ("  report\x00 name.docx  ", "report name.docx"),
        ("CON.docx", "template-CON.docx"),
        ("", "template.docx"),
    ],
)
def test_display_filename_is_sanitized_without_becoming_a_storage_path(
    unsafe: str, safe: str
) -> None:
    assert sanitize_template_display_filename(unsafe) == safe


def test_template_storage_is_private_and_uses_restrictive_permissions(tmp_path: Path) -> None:
    storage = PrivateFileSystemStorage(location=tmp_path)
    key = build_template_storage_key("synthetic-platform-test", "v1.0")

    saved_key = storage.save(key, ContentFile(b"synthetic-private-template"))
    stored_path = tmp_path / saved_key

    assert stat.S_IMODE(stored_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(stored_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(stored_path.parent.parent.stat().st_mode) == 0o700
    assert os.path.commonpath((stored_path, tmp_path)) == str(tmp_path)
    with pytest.raises(ValueError, match="not accessible"):
        storage.url(saved_key)


@pytest.mark.django_db(transaction=True)
def test_database_enforces_unique_type_version_and_one_active_version(
    user_factory: Callable[..., User],
) -> None:
    uploader = user_factory()
    TemplateVersion.objects.create(**template_values(uploader=uploader))
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            database_bulk_create([TemplateVersion(**template_values(uploader=uploader))])

    first = TemplateVersion.objects.create(**template_values(uploader=uploader, version="v2.0"))
    first.transition_to(TemplateVersion.Status.VALID)
    first.transition_to(TemplateVersion.Status.ACTIVE, actor=uploader)
    second = TemplateVersion.objects.create(**template_values(uploader=uploader, version="v3.0"))
    second.transition_to(TemplateVersion.Status.VALID)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            database_id = TemplateVersion._meta.get_field("id").get_db_prep_value(
                second.pk, connection
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE documents_templateversion "
                    "SET status = %s, activated_by_id = %s, activated_at = %s WHERE id = %s",
                    [TemplateVersion.Status.ACTIVE, uploader.pk, timezone.now(), database_id],
                )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"type_key": "unknown-type"}, "type_key"),
        ({"version": "../../unsafe"}, "version"),
        ({"checksum_sha256": "A" * 64}, "checksum_sha256"),
        ({"checksum_sha256": "a" * 63}, "checksum_sha256"),
        ({"byte_size": 0}, "byte_size"),
        ({"byte_size": 10 * 1024 * 1024 + 1}, "byte_size"),
        ({"storage_key": "../../outside.docx"}, "storage_key"),
        (
            {
                "storage_key": build_template_storage_key(
                    "synthetic-platform-test", "different-version"
                )
            },
            "storage_key",
        ),
        ({"original_filename": "x" * 151}, "original_filename"),
        ({"approval_reference": ""}, "approval_reference"),
    ],
)
def test_template_metadata_rejects_invalid_identity_file_and_size_values(
    overrides: dict[str, object], field: str, user_factory: Callable[..., User]
) -> None:
    template = TemplateVersion(**template_values(uploader=user_factory(), **overrides))

    with pytest.raises(ValidationError) as error:
        template.full_clean()

    assert field in error.value.message_dict


@pytest.mark.django_db
def test_validation_report_is_bounded_and_structured(
    user_factory: Callable[..., User],
) -> None:
    uploader = user_factory()
    oversized = TemplateVersion(
        **template_values(
            uploader=uploader,
            validation_report={"errors": ["x" * 4097]},
        )
    )
    sensitive_shape = TemplateVersion(
        **template_values(
            uploader=uploader,
            version="v1.1",
            validation_report={"private_path": "/private/synthetic-template.docx"},
        )
    )

    with pytest.raises(ValidationError):
        oversized.full_clean()
    with pytest.raises(ValidationError):
        sensitive_shape.full_clean()
    non_finite = TemplateVersion(
        **template_values(
            uploader=uploader,
            version="v1.2",
            validation_report={"ratio": math.nan},
        )
    )
    with pytest.raises(ValidationError):
        non_finite.full_clean()
    for unsafe_report in (
        "not a report",
        ["not", "structured"],
        {"error": "secret content at /private/case.docx"},
    ):
        template = TemplateVersion(
            **template_values(
                uploader=uploader,
                version=f"unsafe-{type(unsafe_report).__name__}",
                validation_report=unsafe_report,
            )
        )
        with pytest.raises(ValidationError):
            template.full_clean()
    assert len(json.dumps({"summary": "valid"}).encode()) < 4096


@pytest.mark.django_db
def test_identity_and_file_metadata_cannot_be_changed_or_bulk_updated(
    user_factory: Callable[..., User],
) -> None:
    uploader = user_factory()
    template = TemplateVersion.objects.create(**template_values(uploader=uploader))
    immutable_changes = {
        "type_key": "synthetic-other-test",
        "version": "v9.0",
        "storage_key": build_template_storage_key("synthetic-platform-test", "v9.0"),
        "original_filename": "replacement.docx",
        "checksum_sha256": "b" * 64,
        "byte_size": 2048,
        "uploader": user_factory(username="synthetic-other-uploader"),
    }

    for field, value in immutable_changes.items():
        current = TemplateVersion.objects.get(pk=template.pk)
        setattr(current, field, value)
        with pytest.raises(ImmutableTemplateVersionError):
            current.save()

    with pytest.raises(ImmutableTemplateVersionError):
        TemplateVersion.objects.filter(pk=template.pk).update(version="v9.0")
    with pytest.raises(ImmutableTemplateVersionError):
        TemplateVersion.objects.bulk_create(
            [TemplateVersion(**template_values(uploader=uploader, version="v10.0"))]
        )
    with pytest.raises(ImmutableTemplateVersionError):
        TemplateVersion.objects.bulk_update([template], ["status"])


@pytest.mark.django_db
def test_completed_validation_report_cannot_change(
    user_factory: Callable[..., User],
) -> None:
    template = TemplateVersion.objects.create(**template_values(uploader=user_factory()))
    template.validation_report = {
        "schema_version": 1,
        "result": "valid",
        "categories": [],
        "counts": {},
    }
    template.save()
    template.transition_to(TemplateVersion.Status.VALID)
    template.validation_report = {}

    with pytest.raises(ImmutableTemplateVersionError):
        template.save()


@pytest.mark.django_db
def test_template_history_has_no_supported_application_deletion(
    user_factory: Callable[..., User],
) -> None:
    template = TemplateVersion.objects.create(**template_values(uploader=user_factory()))

    with pytest.raises(ImmutableTemplateVersionError):
        template.delete()
    with pytest.raises(ImmutableTemplateVersionError):
        TemplateVersion.objects.filter(pk=template.pk).delete()
    assert TemplateVersion.objects.filter(pk=template.pk).exists()


@pytest.mark.django_db
def test_lifecycle_allows_only_declared_transitions_and_preserves_activation_history(
    user_factory: Callable[..., User],
) -> None:
    actor = user_factory()
    template = TemplateVersion.objects.create(**template_values(uploader=actor))

    with pytest.raises(InvalidTemplateLifecycleTransition):
        template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)

    template.transition_to(TemplateVersion.Status.VALID)
    template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)
    activated_at = template.activated_at
    template.transition_to(TemplateVersion.Status.INACTIVE, actor=actor)
    template.transition_to(TemplateVersion.Status.INACTIVE, actor=actor)

    assert template.status == TemplateVersion.Status.INACTIVE
    assert template.activated_by == actor
    assert template.activated_at == activated_at
    with pytest.raises(InvalidTemplateLifecycleTransition):
        template.transition_to(TemplateVersion.Status.INVALID)


@pytest.mark.django_db(transaction=True)
def test_lifecycle_transition_uses_the_locked_persisted_state(
    user_factory: Callable[..., User],
) -> None:
    actor = user_factory()
    first = TemplateVersion.objects.create(**template_values(uploader=actor))
    stale = TemplateVersion.objects.get(pk=first.pk)

    first.transition_to(TemplateVersion.Status.VALID)
    with pytest.raises(InvalidTemplateLifecycleTransition):
        stale.transition_to(TemplateVersion.Status.INVALID)

    assert TemplateVersion.objects.get(pk=first.pk).status == TemplateVersion.Status.VALID


@pytest.mark.django_db(transaction=True)
def test_transition_ignores_pre_mutated_activation_metadata(
    user_factory: Callable[..., User],
) -> None:
    uploader = user_factory()
    actor = user_factory(username="synthetic-activation-actor")
    attacker = user_factory(username="synthetic-untrusted-actor")
    template = TemplateVersion.objects.create(**template_values(uploader=uploader))
    template.transition_to(TemplateVersion.Status.VALID)
    template.activated_by = attacker
    template.activated_at = timezone.now()

    template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)

    template.refresh_from_db()
    assert template.activated_by == actor


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_protects_template_history_and_lifecycle_from_raw_sql(
    user_factory: Callable[..., User],
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL integration profile.")
    template = TemplateVersion.objects.create(**template_values(uploader=user_factory()))

    statements = (
        ("UPDATE documents_templateversion SET version = %s WHERE id = %s", ["v9", template.pk]),
        ("UPDATE documents_templateversion SET status = %s WHERE id = %s", ["active", template.pk]),
        ("DELETE FROM documents_templateversion WHERE id = %s", [template.pk]),
        (
            "UPDATE documents_templateversion SET validation_report = %s WHERE id = %s",
            [json.dumps({"categories": ["x" * 5000]}), template.pk],
        ),
    )
    for sql, params in statements:
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, cast(Any, params))

    assert TemplateVersion.objects.filter(pk=template.pk).exists()


@pytest.mark.django_db
def test_new_template_cannot_skip_the_uploaded_state(
    user_factory: Callable[..., User],
) -> None:
    template = TemplateVersion(
        **template_values(uploader=user_factory(), status=TemplateVersion.Status.VALID)
    )

    with pytest.raises(InvalidTemplateLifecycleTransition):
        template.save()


@pytest.mark.django_db(transaction=True)
def test_database_rejects_invalid_status_checksum_size_and_activation_metadata(
    user_factory: Callable[..., User],
) -> None:
    uploader = user_factory()
    invalid_rows = (
        {"version": "invalid-status", "status": "unexpected"},
        {"version": "invalid-checksum", "checksum_sha256": "z" * 64},
        {"version": "invalid-size", "byte_size": 0},
        {"version": "invalid-active-metadata", "activated_by": uploader},
    )

    for overrides in invalid_rows:
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                database_bulk_create(
                    [TemplateVersion(**template_values(uploader=uploader, **overrides))]
                )

    wildcard_version = TemplateVersion(
        **template_values(
            uploader=uploader,
            version="v_1",
            storage_key=build_template_storage_key("synthetic-platform-test", "vx1"),
        )
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            database_bulk_create([wildcard_version])

    unsafe_filename = TemplateVersion(
        **template_values(
            uploader=uploader,
            version="unsafe-filename",
            original_filename="../../unsafe.docx",
        )
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            database_bulk_create([unsafe_filename])


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_template_constraints_and_indexes_are_present() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL integration profile.")

    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(
            cursor, TemplateVersion._meta.db_table
        )

    assert constraints["documents_template_type_version_unique"]["unique"] is True
    assert constraints["documents_one_active_template_per_type"]["unique"] is True
    assert constraints["documents_template_status_valid"]["check"] is True
    assert constraints["documents_template_checksum_valid"]["check"] is True
    assert constraints["documents_template_size_valid"]["check"] is True
    assert constraints["documents_template_activation_metadata_valid"]["check"] is True
    assert constraints["documents_template_type_key_format"]["check"] is True
    assert constraints["documents_template_version_format"]["check"] is True
    assert constraints["documents_template_storage_key_format"]["check"] is True
    assert constraints["documents_template_storage_key_identity"]["check"] is True
    assert constraints["documents_template_display_filename_safe"]["check"] is True
