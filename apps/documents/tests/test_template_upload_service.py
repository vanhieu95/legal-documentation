from __future__ import annotations

import hashlib
import io
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied
from django.core.files.storage import storages
from django.core.files.storage.filesystem import FileSystemStorage

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.actions import AuditAction, AuditOutcome
from apps.audit.models import AuditEvent
from apps.documents.limits import MAX_TEMPLATE_BYTES
from apps.documents.models import TemplateVersion
from apps.documents.registry import DocumentRegistry, document_registry
from apps.documents.services import (
    DuplicateTemplateVersion,
    InvalidTemplateUpload,
    TemplateStorageError,
    UnknownOrDisabledDocumentType,
    upload_and_validate_template,
)
from apps.documents.tests.docx_fixtures import minimal_docx, word_document

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _isolated_private_storage(settings: Any, tmp_path: Path) -> None:
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"
    storages._storages.clear()  # type: ignore[attr-defined]


def _actor(user_factory: object) -> User:
    actor = user_factory(username="synthetic-template-administrator")  # type: ignore[operator]
    actor.groups.add(seed_administrator_permissions())
    return actor


def _template_bytes() -> bytes:
    return minimal_docx(
        entries={
            "word/document.xml": word_document(
                (("{{ document.title }}",), ("{{ document.notes|default('') }}",))
            )
        }
    )


def _upload(actor: User, source: object, **overrides: object) -> TemplateVersion:
    values = {
        "actor": actor,
        "type_key": "synthetic-platform-test",
        "version": "v1.0",
        "approval_reference": "SYNTHETIC-APPROVAL-001",
        "uploaded_file": source,
        "original_filename": "../../unsafe-template.docx",
        "correlation_id": "synthetic-upload-correlation",
    }
    values.update(overrides)
    return upload_and_validate_template(**values)  # type: ignore[arg-type]


def test_valid_upload_is_immutable_valid_private_and_audited_once(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    package = _template_bytes()

    template = _upload(actor, io.BytesIO(package))

    assert template.status == TemplateVersion.Status.VALID
    assert template.checksum_sha256 == hashlib.sha256(package).hexdigest()
    assert template.byte_size == len(package)
    assert template.original_filename == "unsafe-template.docx"
    assert template.storage_key.startswith("templates/synthetic-platform-test/v1.0/")
    assert storages["private"].open(template.storage_key, "rb").read() == package
    assert template.validation_report == {
        "schema_version": 1,
        "result": "valid",
        "categories": [],
        "counts": {"synthetic_renders": 2},
    }
    assert list(
        AuditEvent.objects.filter(
            action__in=(AuditAction.TEMPLATE_UPLOADED, AuditAction.TEMPLATE_VALIDATED)
        ).values_list("action", "outcome")
    ) == [
        (AuditAction.TEMPLATE_UPLOADED, AuditOutcome.SUCCESS),
        (AuditAction.TEMPLATE_VALIDATED, AuditOutcome.SUCCESS),
    ]


def test_invalid_package_is_retained_inactive_with_bounded_safe_report(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    marker = b"synthetic-private-package-content"

    template = _upload(actor, io.BytesIO(marker))

    assert template.status == TemplateVersion.Status.INVALID
    assert storages["private"].open(template.storage_key, "rb").read() == marker
    report_text = str(template.validation_report)
    assert marker.decode() not in report_text
    assert template.storage_key not in report_text
    assert template.validation_report["categories"] == ["not_zip"]
    assert AuditEvent.objects.filter(action=AuditAction.TEMPLATE_UPLOADED).count() == 1
    assert (
        AuditEvent.objects.filter(
            action=AuditAction.TEMPLATE_VALIDATED, outcome=AuditOutcome.FAILURE
        ).count()
        == 1
    )


@pytest.mark.parametrize("type_key", ["synthetic-unknown", "../../unsafe"])
def test_unknown_registry_key_is_rejected_before_storage(
    user_factory: object, type_key: str
) -> None:
    actor = _actor(user_factory)

    with pytest.raises(UnknownOrDisabledDocumentType):
        _upload(actor, io.BytesIO(_template_bytes()), type_key=type_key)

    assert TemplateVersion.objects.count() == 0


def test_duplicate_version_and_missing_approval_are_rejected_before_storage(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    _upload(actor, io.BytesIO(_template_bytes()))

    with pytest.raises(DuplicateTemplateVersion):
        _upload(actor, io.BytesIO(_template_bytes()))
    with pytest.raises(InvalidTemplateUpload):
        _upload(
            actor,
            io.BytesIO(_template_bytes()),
            version="v2.0",
            approval_reference="   ",
        )
    assert TemplateVersion.objects.count() == 1


def test_service_requires_both_upload_and_validation_permissions(user_factory: object) -> None:
    actor = user_factory(username="synthetic-template-outsider")  # type: ignore[operator]

    with pytest.raises(PermissionDenied):
        _upload(actor, io.BytesIO(_template_bytes()))

    assert TemplateVersion.objects.count() == 0


def test_service_denies_administrator_missing_validation_permission(user_factory: object) -> None:
    actor = _actor(user_factory)
    actor.user_permissions.add(Permission.objects.get(codename="upload_templates"))
    actor.groups.clear()

    with pytest.raises(PermissionDenied):
        _upload(actor, io.BytesIO(_template_bytes()))

    assert TemplateVersion.objects.count() == 0


def test_disabled_registry_key_is_rejected_before_storage(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    disabled = document_registry.get("synthetic-platform-test")
    monkeypatch.setattr(
        "apps.documents.services.document_registry",
        DocumentRegistry((replace(disabled, enabled=False),)),
    )

    with pytest.raises(UnknownOrDisabledDocumentType):
        _upload(actor, io.BytesIO(_template_bytes()))

    assert TemplateVersion.objects.count() == 0


def test_compressed_upload_limit_accepts_boundary_and_rejects_one_byte_over(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)

    boundary = _upload(actor, io.BytesIO(b"x" * MAX_TEMPLATE_BYTES), version="v8.0")
    assert boundary.byte_size == MAX_TEMPLATE_BYTES
    assert boundary.status == TemplateVersion.Status.INVALID

    with pytest.raises(InvalidTemplateUpload):
        _upload(actor, io.BytesIO(b"x" * (MAX_TEMPLATE_BYTES + 1)), version="v9.0")
    assert not TemplateVersion.objects.filter(version="v9.0").exists()


class _InterruptedUpload:
    name = "synthetic.docx"

    def read(self, _size: int) -> bytes:
        raise OSError("synthetic sensitive read detail")


def test_interrupted_upload_creates_no_version_or_temporary_file(
    user_factory: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    process_root = tmp_path / "process"
    process_root.mkdir()
    monkeypatch.setattr("apps.documents.services.tempfile.tempdir", str(process_root))

    with pytest.raises(InvalidTemplateUpload):
        _upload(actor, _InterruptedUpload())

    assert TemplateVersion.objects.count() == 0
    assert list(process_root.iterdir()) == []


def test_storage_interruption_removes_partial_storage_and_temporary_files(
    user_factory: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    storage = cast(FileSystemStorage, storages["private"])
    original_save = storage.save
    process_root = tmp_path / "process"
    process_root.mkdir()

    def interrupted_save(name: str, content: object, *args: object, **kwargs: object) -> str:
        original_save(name, content, *args, **kwargs)  # type: ignore[arg-type]
        raise OSError("synthetic private storage detail")

    monkeypatch.setattr(storage, "save", interrupted_save)
    monkeypatch.setattr("apps.documents.services.tempfile.tempdir", str(process_root))

    with pytest.raises(TemplateStorageError):
        _upload(actor, io.BytesIO(_template_bytes()), version="v3.0")

    assert TemplateVersion.objects.count() == 0
    assert list(process_root.iterdir()) == []
    assert not any(path.is_file() for path in Path(storage.location).rglob("*.docx"))


def test_package_failure_short_circuits_jinja_and_rendering(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    template_validator = Mock(side_effect=AssertionError("Jinja must not run"))
    renderer = Mock(side_effect=AssertionError("render must not run"))
    monkeypatch.setattr("apps.documents.services.validate_template", template_validator)
    monkeypatch.setattr("apps.documents.services._render_and_inspect", renderer)

    template = _upload(actor, io.BytesIO(b"not-a-docx"), version="v4.0")

    assert template.status == TemplateVersion.Status.INVALID
    template_validator.assert_not_called()
    renderer.assert_not_called()


def test_split_run_failure_happens_before_rendering(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    split = minimal_docx(
        entries={"word/document.xml": word_document((("{{ document.", "title }}"),))}
    )
    renderer = Mock(side_effect=AssertionError("render must not run"))
    monkeypatch.setattr("apps.documents.services._render_and_inspect", renderer)

    template = _upload(actor, io.BytesIO(split), version="v5.0")

    assert template.status == TemplateVersion.Status.INVALID
    assert "split_token" in template.validation_report["categories"]
    renderer.assert_not_called()


def test_render_interruption_is_durable_invalid_safe_and_cleans_temporary_files(
    user_factory: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    process_root = tmp_path / "process"
    process_root.mkdir()
    monkeypatch.setattr("apps.documents.services.tempfile.tempdir", str(process_root))
    monkeypatch.setattr(
        "apps.documents.services._render_and_inspect",
        Mock(side_effect=RuntimeError("synthetic private render detail")),
    )

    template = _upload(actor, io.BytesIO(_template_bytes()), version="v6.0")

    assert template.status == TemplateVersion.Status.INVALID
    assert template.validation_report["categories"] == ["render_error"]
    assert "private render detail" not in str(template.validation_report)
    assert list(process_root.iterdir()) == []


def test_both_synthetic_outputs_are_reopened_and_meaningfully_inspected(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    inspection = Mock(wraps=None)
    from apps.documents import services

    original = services._inspect_rendered_output

    def recording_inspection(*args: object, **kwargs: object) -> tuple[str, ...]:
        inspection(*args, **kwargs)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(services, "_inspect_rendered_output", recording_inspection)

    template = _upload(actor, io.BytesIO(_template_bytes()), version="v7.0")

    assert template.status == TemplateVersion.Status.VALID
    assert inspection.call_count == 2
