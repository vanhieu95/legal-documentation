from __future__ import annotations

import logging
import math
import tempfile
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import TypedDict, cast
from uuid import UUID, uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.cases.models import CaseParticipant, CaseRecord
from apps.cases.policies import case_object_policy
from apps.documents import generation_reservations
from apps.documents.generation_reservations import (
    GenerationReservationConflict,
    GenerationReservationUnavailable,
    InvalidIdempotencyKey,
    issue_generation_idempotency_key,
    reserve_generation,
)
from apps.documents.models import DocumentDraft, GeneratedDocument, TemplateVersion
from apps.documents.registry import document_registry
from apps.documents.tests.test_template_versions import template_values
from tests.factories import CaseParticipantFactory, CaseRecordFactory

pytestmark = pytest.mark.django_db


class _ReservationArguments(TypedDict):
    actor: User
    case_id: UUID
    draft_id: UUID
    expected_case_revision: int
    expected_draft_revision: int
    expected_template_id: UUID
    idempotency_key: str
    correlation_id: str


def _actor(user_factory: object, username: str = "synthetic-generation-admin") -> User:
    actor = user_factory(username=username)  # type: ignore[operator]
    actor.groups.add(seed_administrator_permissions())
    return actor


def test_application_issued_tokens_are_random_opaque_and_bounded() -> None:
    first = issue_generation_idempotency_key()
    second = issue_generation_idempotency_key()

    assert first != second
    assert len(first) == len(second) == 43
    assert first.replace("-", "").replace("_", "").isalnum()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (date(2026, 9, 14), "2026-09-14"),
        (datetime(2026, 9, 14, 1, 2, tzinfo=UTC), "2026-09-14T01:02:00+00:00"),
        (Decimal("10.50"), "10.50"),
        ({"nested": (1, "hai")}, {"nested": [1, "hai"]}),
    ],
)
def test_snapshot_json_conversion_is_explicit(raw: object, expected: object) -> None:
    assert generation_reservations._json_value(raw) == expected


@pytest.mark.parametrize("raw", [{1: "bad key"}, object(), math.nan])
def test_snapshot_json_conversion_rejects_unsupported_values(raw: object) -> None:
    with pytest.raises(GenerationReservationUnavailable):
        generation_reservations._json_value(raw)


def _case(actor: User) -> CaseRecord:
    return cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))


def _active_template(actor: User, *, version: str = "generation-v1") -> TemplateVersion:
    template = TemplateVersion.objects.create(**template_values(uploader=actor, version=version))
    template.validation_report = {
        "schema_version": 1,
        "result": "valid",
        "categories": [],
        "counts": {"synthetic_renders": 2},
    }
    template.save(update_fields=("validation_report",))
    template.transition_to(TemplateVersion.Status.VALID)
    template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)
    return template


def _ready_draft(
    actor: User,
    case: CaseRecord,
    *,
    payload: dict[str, object] | None = None,
) -> DocumentDraft:
    return DocumentDraft.objects.create(
        case=case,
        type_key="synthetic-platform-test",
        schema_version="v1",
        payload={
            "title": "Giá trị văn bản",
            "notes": "Ghi chú tổng hợp",
            "participant_id": None,
        }
        if payload is None
        else payload,
        state=DocumentDraft.State.READY,
        revision=1,
        created_by=actor,
        last_edited_by=actor,
    )


def _reserve(
    actor: User,
    case: CaseRecord,
    draft: DocumentDraft,
    template: TemplateVersion,
    *,
    token: str | None = None,
    case_revision: int | None = None,
    draft_revision: int | None = None,
    correlation_id: str = "generation-reservation-test",
) -> GeneratedDocument:
    return reserve_generation(
        actor=actor,
        case_id=case.pk,
        draft_id=draft.pk,
        type_key=draft.type_key,
        schema_version=draft.schema_version,
        expected_case_revision=case.revision if case_revision is None else case_revision,
        expected_draft_revision=draft.revision if draft_revision is None else draft_revision,
        expected_template_id=template.pk,
        idempotency_key=issue_generation_idempotency_key() if token is None else token,
        correlation_id=correlation_id,
    )


def test_valid_reservation_freezes_exact_facts_and_safe_audit(user_factory: object) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    participant = cast(CaseParticipant, CaseParticipantFactory(case=case))
    case.matter_type = "Việc dân sự tổng hợp"
    case.save(update_fields=("matter_type",))
    draft = _ready_draft(
        actor,
        case,
        payload={
            "title": "Nội dung đã ghi đè",
            "notes": "Ghi chú",
            "participant_id": str(participant.pk),
        },
    )
    template = _active_template(actor)

    attempt = _reserve(actor, case, draft, template)

    assert attempt.status == GeneratedDocument.Status.GENERATING
    assert attempt.case == case
    assert attempt.type_key == "synthetic-platform-test"
    assert attempt.schema_version == "v1"
    assert attempt.template_version == template
    assert attempt.actor == actor
    assert attempt.source_draft_id == draft.pk
    assert attempt.case_revision == case.revision
    assert attempt.draft_revision == draft.revision
    assert attempt.input_snapshot == {"version": 1, "values": draft.payload}
    assert attempt.resolved_values_snapshot == {
        "version": 1,
        "values": {
            "participant_id": str(participant.pk),
            "title": "Việc dân sự tổng hợp",
        },
    }
    assert attempt.override_snapshot == {
        "version": 1,
        "values": {
            "title": {
                "case_value": "Việc dân sự tổng hợp",
                "draft_value": "Nội dung đã ghi đè",
                "source": "case.matter_type",
            }
        },
    }
    assert attempt.template_snapshot == {
        "version": 1,
        "identity": {
            "id": str(template.pk),
            "type_key": template.type_key,
            "version": template.version,
            "checksum_sha256": template.checksum_sha256,
        },
    }
    event = AuditEvent.objects.get(action=AuditAction.DOCUMENT_GENERATION_RESERVED)
    assert event.target_id == str(attempt.pk)
    assert event.metadata == {
        "case_revision": case.revision,
        "draft_revision": draft.revision,
        "schema_version": "v1",
        "template_version": template.version,
        "type_key": template.type_key,
    }
    assert "snapshot" not in str(event.metadata).casefold()


def test_sequential_idempotency_returns_unchanged_attempt_and_one_audit(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)
    token = issue_generation_idempotency_key()
    first = _reserve(actor, case, draft, template, token=token)

    case.matter_type = "Later case edit"
    case.revision += 1
    case.save(update_fields=("matter_type", "revision"))
    draft.payload = {**draft.payload, "title": "Later draft edit"}
    draft.revision += 1
    draft.save(update_fields=("payload", "revision"))
    template.transition_to(TemplateVersion.Status.INACTIVE)
    replacement = _active_template(actor, version="generation-v2")

    second = _reserve(
        actor,
        case,
        draft,
        replacement,
        token=token,
        case_revision=case.revision,
        draft_revision=draft.revision,
    )

    assert second.pk == first.pk
    second.refresh_from_db()
    assert second.input_snapshot == first.input_snapshot
    assert second.resolved_values_snapshot == first.resolved_values_snapshot
    assert second.template_version_id == template.pk
    assert GeneratedDocument.objects.count() == 1
    assert AuditEvent.objects.filter(action=AuditAction.DOCUMENT_GENERATION_RESERVED).count() == 1


def test_distinct_tokens_create_distinct_attempts(user_factory: object) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)

    first = _reserve(actor, case, draft, template)
    second = _reserve(actor, case, draft, template)

    assert first.pk != second.pk
    assert GeneratedDocument.objects.count() == 2


@pytest.mark.parametrize("token", ["", "short", "x" * 44, "!" * 43])
def test_token_is_opaque_bounded_and_validated(user_factory: object, token: str) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)

    with pytest.raises(InvalidIdempotencyKey):
        _reserve(actor, case, draft, template, token=token)


def test_token_scope_cannot_return_another_actor_attempt(user_factory: object) -> None:
    first_actor = _actor(user_factory, "first-generation-admin")
    second_actor = _actor(user_factory, "second-generation-admin")
    token = issue_generation_idempotency_key()
    first_case = _case(first_actor)
    first = _reserve(
        first_actor,
        first_case,
        _ready_draft(first_actor, first_case),
        _active_template(first_actor),
        token=token,
    )
    second_case = _case(second_actor)

    second = _reserve(
        second_actor,
        second_case,
        _ready_draft(second_actor, second_case),
        first.template_version,
        token=token,
    )

    assert second.pk != first.pk


def test_same_actor_token_reuse_for_different_request_is_a_conflict(user_factory: object) -> None:
    actor = _actor(user_factory)
    template = _active_template(actor)
    token = issue_generation_idempotency_key()
    first_case = _case(actor)
    _reserve(actor, first_case, _ready_draft(actor, first_case), template, token=token)
    second_case = _case(actor)

    with pytest.raises(GenerationReservationConflict):
        _reserve(actor, second_case, _ready_draft(actor, second_case), template, token=token)


@pytest.mark.parametrize("stale", ["case", "draft"])
def test_stale_revisions_are_conflicts(user_factory: object, stale: str) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)

    with pytest.raises(GenerationReservationConflict):
        _reserve(
            actor,
            case,
            draft,
            template,
            case_revision=case.revision - 1 if stale == "case" else case.revision,
            draft_revision=draft.revision - 1 if stale == "draft" else draft.revision,
        )


def test_invalid_incompatible_or_nonready_draft_is_rejected(user_factory: object) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    template = _active_template(actor)
    draft = _ready_draft(actor, case)
    DocumentDraft.objects.filter(pk=draft.pk).update(
        payload={"notes": "missing title"}, state=DocumentDraft.State.DRAFT
    )
    draft.refresh_from_db()

    with pytest.raises(GenerationReservationUnavailable):
        _reserve(actor, case, draft, template)


def test_unknown_disabled_type_and_inactive_or_changed_template_are_rejected(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)
    registration = document_registry.get(draft.type_key)
    monkeypatch.setattr(document_registry, "get", lambda _key: replace(registration, enabled=False))
    with pytest.raises(GenerationReservationUnavailable):
        _reserve(actor, case, draft, template)


def test_unknown_type_incompatible_schema_missing_draft_and_no_active_template_are_rejected(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)
    common: _ReservationArguments = {
        "actor": actor,
        "case_id": case.pk,
        "draft_id": draft.pk,
        "expected_case_revision": case.revision,
        "expected_draft_revision": draft.revision,
        "expected_template_id": template.pk,
        "idempotency_key": issue_generation_idempotency_key(),
        "correlation_id": "generation-unavailable-test",
    }
    with pytest.raises(GenerationReservationUnavailable):
        reserve_generation(type_key="unknown-type", schema_version="v1", **common)
    with pytest.raises(GenerationReservationUnavailable):
        reserve_generation(type_key=draft.type_key, schema_version="v2", **common)
    missing_draft: _ReservationArguments = {**common, "draft_id": uuid4()}
    with pytest.raises(GenerationReservationUnavailable):
        reserve_generation(
            type_key=draft.type_key,
            schema_version=draft.schema_version,
            **missing_draft,
        )

    template.transition_to(TemplateVersion.Status.INACTIVE)
    with pytest.raises(GenerationReservationUnavailable):
        _reserve(actor, case, draft, template)


def test_invalid_active_template_report_is_rejected(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    template = _active_template(actor)
    template.validation_report = {"result": "invalid"}
    fake_queryset = SimpleNamespace(get=lambda **_kwargs: template)
    monkeypatch.setattr(
        TemplateVersion.objects,
        "select_for_update",
        lambda: fake_queryset,
    )

    with pytest.raises(GenerationReservationUnavailable):
        generation_reservations._active_template(
            type_key=template.type_key,
            expected_template_id=template.pk,
        )


def test_ready_but_invalid_draft_and_unrelated_integrity_conflict_are_safe(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)
    DocumentDraft.objects.filter(pk=draft.pk).update(payload={"notes": "missing title"})
    draft.refresh_from_db()
    with pytest.raises(GenerationReservationUnavailable):
        _reserve(actor, case, draft, template)

    DocumentDraft.objects.filter(pk=draft.pk).update(
        payload={"title": "Restored", "notes": "", "participant_id": None}
    )
    draft.refresh_from_db()
    monkeypatch.setattr(
        GeneratedDocument,
        "save",
        lambda self: (_ for _ in ()).throw(IntegrityError("synthetic conflict")),
    )
    with pytest.raises(GenerationReservationConflict) as captured:
        _reserve(actor, case, draft, template)
    assert captured.value.__cause__ is None

    monkeypatch.undo()
    template.transition_to(TemplateVersion.Status.INACTIVE)
    _active_template(actor, version="generation-v2")
    with pytest.raises(GenerationReservationConflict):
        _reserve(actor, case, draft, template)


def test_archived_inaccessible_and_direct_unauthorized_calls_are_denied(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)
    case.status = CaseRecord.Status.ARCHIVED
    case.archived_by = actor
    case.archived_at = timezone.now()
    case.archive_reason = "Synthetic archive"
    case.save()
    with pytest.raises(PermissionDenied):
        _reserve(actor, case, draft, template)

    case.status = CaseRecord.Status.ACTIVE
    case.archived_by = None
    case.archived_at = None
    case.archive_reason = ""
    case.save()
    monkeypatch.setattr(
        case_object_policy,
        "scope_queryset",
        lambda _actor, queryset: queryset.none(),
    )
    with pytest.raises(PermissionDenied):
        _reserve(actor, case, draft, template)

    monkeypatch.undo()
    group = actor.groups.get(name="Administrator")
    group.permissions.remove(Permission.objects.get(codename="generate_documents"))
    denied_actor = User.objects.get(pk=actor.pk)
    with pytest.raises(PermissionDenied):
        _reserve(denied_actor, case, draft, template)


def test_duplicate_token_does_not_bypass_later_case_archival(user_factory: object) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)
    token = issue_generation_idempotency_key()
    _reserve(actor, case, draft, template, token=token)
    case.status = CaseRecord.Status.ARCHIVED
    case.archived_by = actor
    case.archived_at = timezone.now()
    case.archive_reason = "Synthetic archive"
    case.save()

    with pytest.raises(PermissionDenied):
        _reserve(actor, case, draft, template, token=token)


def test_reservation_performs_no_file_or_render_work(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)
    monkeypatch.setattr(
        tempfile,
        "NamedTemporaryFile",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no temp files")),
    )

    attempt = _reserve(actor, case, draft, template)

    assert attempt.output_storage_key == ""


def test_logs_and_audit_do_not_contain_token_or_snapshot_values(
    user_factory: object, caplog: pytest.LogCaptureFixture
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    secret_value = "SYNTHETIC-SENSITIVE-VALUE"
    draft = _ready_draft(actor, case, payload={"title": secret_value})
    template = _active_template(actor)
    token = issue_generation_idempotency_key()

    with caplog.at_level(logging.DEBUG):
        _reserve(
            actor,
            case,
            draft,
            template,
            token=token,
            correlation_id=token,
        )

    events = list(AuditEvent.objects.values("correlation_id", "metadata", "changed_fields"))
    captured = caplog.text + str(events)
    assert token not in captured
    assert secret_value not in captured
    assert "idempotency" not in captured.casefold()
