from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.cases.models import CaseRecord
from apps.documents.models import (
    GeneratedDocument,
    ImmutableGeneratedDocumentError,
    TemplateVersion,
)
from apps.documents.tests.test_template_versions import template_values
from tests.factories import CaseRecordFactory, UserFactory

pytestmark = pytest.mark.django_db


def _attempt() -> GeneratedDocument:
    actor = cast(User, UserFactory())
    case = cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))
    template = TemplateVersion.objects.create(**template_values(uploader=actor))
    return GeneratedDocument.objects.create(
        case=case,
        type_key="synthetic-platform-test",
        template_version=template,
        schema_version="v1",
        source_draft_id=case.pk,
        case_revision=case.revision,
        draft_revision=1,
        input_snapshot={"version": 1, "values": {"title": "Synthetic"}},
        resolved_values_snapshot={"version": 1, "values": {"title": "Matter"}},
        override_snapshot={"version": 1, "values": {}},
        template_snapshot={
            "version": 1,
            "identity": {
                "id": str(template.pk),
                "type_key": template.type_key,
                "version": template.version,
                "checksum_sha256": template.checksum_sha256,
            },
        },
        actor=actor,
        idempotency_key_hash="a" * 64,
    )


def _database_bulk_create(attempt: GeneratedDocument) -> None:
    models.QuerySet.bulk_create(GeneratedDocument.objects.all(), [attempt])


def test_new_attempt_defaults_to_generating_without_artifact_or_failure() -> None:
    attempt = _attempt()

    assert attempt.status == GeneratedDocument.Status.GENERATING
    assert attempt.reserved_at is not None
    assert attempt.generated_at is None
    assert attempt.failed_at is None
    assert attempt.output_storage_key == ""
    assert attempt.output_filename == ""
    assert attempt.output_size is None
    assert attempt.output_checksum_sha256 == ""
    assert attempt.failure_category == ""
    assert attempt.failure_correlation_id == ""


def test_reservation_facts_and_history_cannot_be_rewritten_or_deleted() -> None:
    attempt = _attempt()
    attempt.input_snapshot = {"version": 1, "values": {"title": "Changed"}}

    with pytest.raises(ImmutableGeneratedDocumentError):
        attempt.save()
    with pytest.raises(ImmutableGeneratedDocumentError):
        GeneratedDocument.objects.filter(pk=attempt.pk).update(draft_revision=2)
    with pytest.raises(ImmutableGeneratedDocumentError):
        attempt.delete()


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "unknown"},
        {"output_storage_key": "generated/premature.docx"},
        {"status": "generated"},
        {
            "status": "failed",
            "failure_category": "render_error",
            "failure_correlation_id": "failure-1",
        },
    ],
)
def test_status_dependent_database_constraints_reject_incomplete_rows(
    overrides: dict[str, object],
) -> None:
    base = _attempt()
    candidate = GeneratedDocument(
        case=base.case,
        type_key=base.type_key,
        template_version=base.template_version,
        schema_version=base.schema_version,
        source_draft_id=base.source_draft_id,
        case_revision=base.case_revision,
        draft_revision=base.draft_revision,
        input_snapshot=base.input_snapshot,
        resolved_values_snapshot=base.resolved_values_snapshot,
        override_snapshot=base.override_snapshot,
        template_snapshot=base.template_snapshot,
        actor=base.actor,
        idempotency_key_hash=("b" * 63) + str(len(overrides)),
        **overrides,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        _database_bulk_create(candidate)


def test_template_reference_is_protected() -> None:
    attempt = _attempt()

    with pytest.raises(models.ProtectedError):
        models.QuerySet.delete(TemplateVersion.objects.filter(pk=attempt.template_version_id))


def test_snapshot_envelopes_are_versioned_and_bounded() -> None:
    attempt = _attempt()
    invalid_snapshots = (
        ["not", "an", "object"],
        {"version": "1", "values": {}},
        {"version": True, "values": {}},
        {"version": 2, "values": {}},
        {"version": 1, "values": {"field": "x" * 70_000}},
        {"version": 1, "values": {"field": "invalid\ud800unicode"}},
    )
    for snapshot in invalid_snapshots:
        candidate = GeneratedDocument(
            case=attempt.case,
            type_key=attempt.type_key,
            template_version=attempt.template_version,
            schema_version=attempt.schema_version,
            source_draft_id=attempt.source_draft_id,
            case_revision=1,
            draft_revision=1,
            input_snapshot=snapshot,
            resolved_values_snapshot={"version": 1, "values": {}},
            override_snapshot={"version": 1, "values": {}},
            template_snapshot=attempt.template_snapshot,
            actor=attempt.actor,
            idempotency_key_hash="b" * 64,
        )
        with pytest.raises(ValidationError):
            candidate.full_clean()


def test_idempotency_hash_is_unique_within_actor_scope() -> None:
    attempt = _attempt()
    duplicate = GeneratedDocument(
        case=attempt.case,
        type_key=attempt.type_key,
        template_version=attempt.template_version,
        schema_version=attempt.schema_version,
        source_draft_id=attempt.source_draft_id,
        case_revision=attempt.case_revision,
        draft_revision=attempt.draft_revision,
        input_snapshot=attempt.input_snapshot,
        resolved_values_snapshot=attempt.resolved_values_snapshot,
        override_snapshot=attempt.override_snapshot,
        template_snapshot=attempt.template_snapshot,
        actor=attempt.actor,
        idempotency_key_hash=attempt.idempotency_key_hash,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        _database_bulk_create(duplicate)


@pytest.mark.parametrize(
    "unsafe",
    [
        {"output_filename": "../../unsafe.docx"},
        {"output_storage_key": "../public/unsafe.docx"},
        {"output_storage_key": f"generated/{uuid4()}/{uuid4()}/synthetic.docx"},
        {"output_size": None},
    ],
)
def test_generated_output_metadata_must_be_complete_and_safe(
    unsafe: dict[str, object],
) -> None:
    attempt = _attempt()
    values: dict[str, object] = {
        "status": GeneratedDocument.Status.GENERATED,
        "generated_at": timezone.now(),
        "output_storage_key": f"generated/{attempt.case_id}/{attempt.pk}/synthetic.docx",
        "output_filename": "synthetic.docx",
        "output_size": 12,
        "output_checksum_sha256": "c" * 64,
    }
    values.update(unsafe)

    with pytest.raises(IntegrityError), transaction.atomic():
        models.QuerySet.update(GeneratedDocument.objects.filter(pk=attempt.pk), **values)


def test_complete_generated_output_metadata_satisfies_database_constraints() -> None:
    attempt = _attempt()

    updated = models.QuerySet.update(
        GeneratedDocument.objects.filter(pk=attempt.pk),
        status=GeneratedDocument.Status.GENERATED,
        generated_at=timezone.now(),
        output_storage_key=f"generated/{attempt.case_id}/{attempt.pk}/synthetic.docx",
        output_filename="synthetic.docx",
        output_size=12,
        output_checksum_sha256="c" * 64,
    )

    assert updated == 1


def test_failed_attempt_requires_safe_failure_metadata_and_no_output() -> None:
    attempt = _attempt()
    with pytest.raises(IntegrityError), transaction.atomic():
        models.QuerySet.update(
            GeneratedDocument.objects.filter(pk=attempt.pk),
            status=GeneratedDocument.Status.FAILED,
            failed_at=timezone.now(),
            failure_category=GeneratedDocument.FailureCategory.RENDER_ERROR,
            failure_correlation_id="unsafe\ncorrelation",
        )


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_generation_guards_and_indexes_are_present() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL generation constraints.")
    attempt = _attempt()
    table_name = GeneratedDocument._meta.db_table
    table = connection.ops.quote_name(table_name)
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET input_snapshot = %s::jsonb WHERE id = %s",
            ['{"version":1,"values":{"title":"changed"}}', attempt.pk],
        )
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE id = %s", [attempt.pk])
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET resolved_values_snapshot = %s::jsonb WHERE id = %s",
            ["[]", attempt.pk],
        )
    malformed = GeneratedDocument(
        case=attempt.case,
        type_key=attempt.type_key,
        template_version=attempt.template_version,
        schema_version=attempt.schema_version,
        source_draft_id=attempt.source_draft_id,
        case_revision=attempt.case_revision,
        draft_revision=attempt.draft_revision,
        input_snapshot={},
        resolved_values_snapshot={"version": 1, "values": {}},
        override_snapshot={"version": 1, "values": {}},
        template_snapshot=attempt.template_snapshot,
        actor=attempt.actor,
        idempotency_key_hash="d" * 64,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        _database_bulk_create(malformed)
    for malformed_snapshot in (
        {"version": "1", "values": {}},
        {
            "version": 1,
            "identity": {},
        },
    ):
        malformed = GeneratedDocument(
            case=attempt.case,
            type_key=attempt.type_key,
            template_version=attempt.template_version,
            schema_version=attempt.schema_version,
            source_draft_id=attempt.source_draft_id,
            case_revision=attempt.case_revision,
            draft_revision=attempt.draft_revision,
            input_snapshot=(
                malformed_snapshot if "values" in malformed_snapshot else attempt.input_snapshot
            ),
            resolved_values_snapshot=attempt.resolved_values_snapshot,
            override_snapshot=attempt.override_snapshot,
            template_snapshot=(
                malformed_snapshot
                if "identity" in malformed_snapshot
                else attempt.template_snapshot
            ),
            actor=attempt.actor,
            idempotency_key_hash=("e" if "values" in malformed_snapshot else "f") * 64,
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            _database_bulk_create(malformed)

    mismatched = GeneratedDocument(
        case=attempt.case,
        type_key="vds-01",
        template_version=attempt.template_version,
        schema_version=attempt.schema_version,
        source_draft_id=attempt.source_draft_id,
        case_revision=attempt.case_revision,
        draft_revision=attempt.draft_revision,
        input_snapshot=attempt.input_snapshot,
        resolved_values_snapshot=attempt.resolved_values_snapshot,
        override_snapshot=attempt.override_snapshot,
        template_snapshot=attempt.template_snapshot,
        actor=attempt.actor,
        idempotency_key_hash="1" * 64,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        _database_bulk_create(mismatched)

    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table_name)
    assert constraints["documents_generation_actor_idempotency_unique"]["unique"] is True
    assert constraints["documents_generation_status_metadata_valid"]["check"] is True
    assert constraints["documents_generation_snapshots_valid"]["check"] is True
    assert constraints["doc_gen_case_history_idx"]["index"] is True
    assert constraints["doc_generation_type_status_idx"]["index"] is True
