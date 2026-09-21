from __future__ import annotations

import json
from typing import cast

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from apps.cases.models import CaseRecord
from apps.documents.models import DocumentDraft, ImmutableDocumentDraftIdentityError
from tests.factories import CaseRecordFactory, UserFactory

pytestmark = pytest.mark.django_db


def _draft() -> DocumentDraft:
    actor = cast(User, UserFactory())
    case = cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))
    return DocumentDraft.objects.create(
        case=case,
        type_key="synthetic-platform-test",
        schema_version="v1",
        payload={"title": "Synthetic"},
        state=DocumentDraft.State.DRAFT,
        revision=1,
        created_by=actor,
        last_edited_by=actor,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("state", "unknown"), ("revision", 0)],
)
def test_state_and_revision_constraints(field: str, value: object) -> None:
    draft = _draft()
    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentDraft.objects.filter(pk=draft.pk).update(**{field: value})


def test_one_draft_per_case_type_and_schema() -> None:
    draft = _draft()
    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentDraft.objects.bulk_create(
            [
                DocumentDraft(
                    case=draft.case,
                    type_key=draft.type_key,
                    schema_version=draft.schema_version,
                    payload={"title": "Duplicate"},
                    state=DocumentDraft.State.DRAFT,
                    revision=1,
                    created_by=draft.created_by,
                    last_edited_by=draft.last_edited_by,
                )
            ]
        )


@pytest.mark.parametrize("field_name", ["case", "participants", "snapshot"])
def test_model_rejects_case_graph_and_snapshot_payload_keys(field_name: str) -> None:
    actor = cast(User, UserFactory())
    case = cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))
    with pytest.raises(ValidationError):
        DocumentDraft.objects.create(
            case=case,
            type_key="synthetic-platform-test",
            schema_version="v1",
            payload={"title": "Synthetic", field_name: {}},
            state=DocumentDraft.State.DRAFT,
            revision=1,
            created_by=actor,
            last_edited_by=actor,
        )


@pytest.mark.parametrize("field", ["type_key", "schema_version", "case_id"])
def test_draft_identity_cannot_be_rewritten(field: str) -> None:
    draft = _draft()
    replacement: object = "v2"
    if field == "type_key":
        replacement = "synthetic-other-type"
    elif field == "case_id":
        replacement = cast(CaseRecord, CaseRecordFactory()).pk

    with pytest.raises(ImmutableDocumentDraftIdentityError):
        DocumentDraft.objects.filter(pk=draft.pk).update(**{field: replacement})

    setattr(draft, field, replacement)
    with pytest.raises(ImmutableDocumentDraftIdentityError):
        draft.save()


@pytest.mark.postgresql
def test_postgresql_payload_constraint_rejects_oversized_or_non_object_json() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL JSON constraints.")
    draft = _draft()
    table = connection.ops.quote_name(DocumentDraft._meta.db_table)
    for payload in (["not", "an", "object"], {"title": "x" * 70_000}):
        with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET payload = %s::jsonb WHERE id = %s",
                [json.dumps(payload), draft.pk],
            )
