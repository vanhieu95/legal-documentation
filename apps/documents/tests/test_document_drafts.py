from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from typing import Any, cast

import pytest
from django import forms
from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.utils import timezone

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.cases.models import CaseParticipant, CaseRecord
from apps.cases.policies import case_object_policy
from apps.documents.draft_services import (
    DraftPayloadTooLarge,
    DraftRevisionConflict,
    DraftSchemaMismatch,
    DraftValidationError,
    create_document_draft,
    get_document_draft,
    update_document_draft,
    validate_document_draft_payload,
)
from apps.documents.models import DocumentDraft
from apps.documents.registry import (
    DocumentFormBundle,
    RelatedFieldDefinition,
    RelatedObjectKind,
    document_registry,
)
from tests.factories import CaseParticipantFactory, CaseRecordFactory

pytestmark = pytest.mark.django_db


def _actor(user_factory: object, username: str = "synthetic-draft-admin") -> User:
    actor = user_factory(username=username)  # type: ignore[operator]
    actor.groups.add(seed_administrator_permissions())
    return actor


def _case(actor: User) -> CaseRecord:
    return cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))


def _create(
    actor: User,
    case: CaseRecord,
    *,
    payload: dict[str, object] | None = None,
    state: str = DocumentDraft.State.DRAFT,
) -> DocumentDraft:
    return create_document_draft(
        actor=actor,
        case_id=case.pk,
        type_key="synthetic-platform-test",
        schema_version="v1",
        payload={"title": "Synthetic draft"} if payload is None else payload,
        state=state,
        correlation_id="draft-create",
    )


def test_valid_draft_creation_update_and_safe_audit(user_factory: object) -> None:
    actor = _actor(user_factory)
    case = _case(actor)

    draft = _create(actor, case, payload={"title": "Ban đầu", "notes": "Ghi chú"})
    updated = update_document_draft(
        actor=actor,
        draft_id=draft.pk,
        type_key=draft.type_key,
        schema_version=draft.schema_version,
        expected_revision=1,
        payload={"title": "Đã sửa", "notes": "Nhiều dòng\nDòng thứ hai"},
        state=DocumentDraft.State.DRAFT,
        correlation_id="draft-update",
    )

    assert updated.revision == 2
    assert updated.created_by == actor
    assert updated.last_edited_by == actor
    assert updated.created_at <= updated.updated_at
    assert updated.payload == {
        "notes": "Nhiều dòng\nDòng thứ hai",
        "participant_id": None,
        "title": "Đã sửa",
    }
    events = AuditEvent.objects.filter(target_id=str(draft.pk)).order_by("occurred_at")
    assert [event.action for event in events] == [
        AuditAction.DOCUMENT_DRAFT_CREATED,
        AuditAction.DOCUMENT_DRAFT_UPDATED,
    ]
    assert events[0].changed_fields == [
        "notes",
        "participant_id",
        "title",
        "state",
        "revision",
    ]
    assert events[1].changed_fields == ["notes", "title", "revision"]
    serialized = str([(event.changed_fields, event.metadata) for event in events])
    assert "Ban đầu" not in serialized
    assert "Đã sửa" not in serialized
    assert "Nhiều dòng" not in serialized


def test_draft_and_ready_transitions_revalidate(user_factory: object) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _create(actor, case)

    ready = update_document_draft(
        actor=actor,
        draft_id=draft.pk,
        type_key=draft.type_key,
        schema_version=draft.schema_version,
        expected_revision=1,
        payload=draft.payload,
        state=DocumentDraft.State.READY,
        correlation_id="draft-ready",
    )
    reopened = update_document_draft(
        actor=actor,
        draft_id=draft.pk,
        type_key=draft.type_key,
        schema_version=draft.schema_version,
        expected_revision=2,
        payload=ready.payload,
        state=DocumentDraft.State.DRAFT,
        correlation_id="draft-reopen",
    )

    assert reopened.state == DocumentDraft.State.DRAFT
    assert reopened.revision == 3
    assert AuditEvent.objects.filter(action=AuditAction.DOCUMENT_DRAFT_STATE_CHANGED).count() == 2


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": "x" * 201},
        {"title": "Valid", "notes": "x" * 1001},
        {"title": "Valid", "unknown": "not in the schema"},
    ],
)
def test_required_boundary_and_unknown_fields_are_rejected(
    user_factory: object, payload: dict[str, object]
) -> None:
    actor = _actor(user_factory)
    with pytest.raises(DraftValidationError):
        _create(actor, _case(actor), payload=payload)


def test_optional_boundary_unicode_and_template_looking_text_are_plain_data(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    text = "Tiếng Việt\n{{ user.password }}\n<w:t>ordinary text</w:t>"

    draft = _create(
        actor,
        case,
        payload={"title": "Đ" * 200, "notes": text},
    )

    assert draft.payload["title"] == "Đ" * 200
    assert draft.payload["notes"] == text


def test_payload_size_is_bounded_before_form_processing(user_factory: object) -> None:
    actor = _actor(user_factory)
    with pytest.raises(DraftPayloadTooLarge):
        _create(actor, _case(actor), payload={"title": "x" * 70_000})


@pytest.mark.parametrize(
    ("type_key", "schema_version"),
    [("unknown-type", "v1"), ("synthetic-platform-test", "v2")],
)
def test_registry_type_and_schema_mismatch_are_rejected(
    user_factory: object, type_key: str, schema_version: str
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    with pytest.raises(DraftSchemaMismatch):
        create_document_draft(
            actor=actor,
            case_id=case.pk,
            type_key=type_key,
            schema_version=schema_version,
            payload={"title": "Synthetic"},
            state=DocumentDraft.State.DRAFT,
            correlation_id="draft-schema-mismatch",
        )


def test_stale_revision_is_a_recoverable_conflict(user_factory: object) -> None:
    actor = _actor(user_factory)
    draft = _create(actor, _case(actor))
    update_document_draft(
        actor=actor,
        draft_id=draft.pk,
        type_key=draft.type_key,
        schema_version=draft.schema_version,
        expected_revision=1,
        payload={"title": "First winner"},
        state=DocumentDraft.State.DRAFT,
        correlation_id="draft-winner",
    )

    with pytest.raises(DraftRevisionConflict) as captured:
        update_document_draft(
            actor=actor,
            draft_id=draft.pk,
            type_key=draft.type_key,
            schema_version=draft.schema_version,
            expected_revision=1,
            payload={"title": "Stale overwrite"},
            state=DocumentDraft.State.DRAFT,
            correlation_id="draft-stale",
        )

    assert captured.value.status_code == 409
    draft.refresh_from_db()
    assert draft.payload["title"] == "First winner"


def test_related_identifiers_are_requeried_within_the_case(user_factory: object) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    own_participant = cast(CaseParticipant, CaseParticipantFactory(case=case))
    other_participant = cast(CaseParticipant, CaseParticipantFactory())

    draft = _create(
        actor,
        case,
        payload={"title": "Scoped", "participant_id": str(own_participant.pk)},
    )
    assert draft.payload["participant_id"] == str(own_participant.pk)
    with pytest.raises(DraftValidationError):
        _create(
            actor,
            _case(actor),
            payload={"title": "Cross case", "participant_id": str(other_participant.pk)},
        )


def test_archived_and_policy_inaccessible_cases_reject_writes(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    archived = _case(actor)
    archived.status = CaseRecord.Status.ARCHIVED
    archived.archived_by = actor
    archived.archived_at = timezone.now()
    archived.archive_reason = "Synthetic archive reason"
    archived.save(update_fields=("status", "archived_by", "archived_at", "archive_reason"))
    with pytest.raises(PermissionDenied):
        _create(actor, archived)

    inaccessible = _case(actor)
    monkeypatch.setattr(
        case_object_policy,
        "scope_queryset",
        lambda _actor, queryset: queryset.none(),
    )
    with pytest.raises(PermissionDenied):
        _create(actor, inaccessible)


@pytest.mark.parametrize(
    ("service", "permission_codename"),
    [("create", "add_document_drafts"), ("read", "view_document_drafts")],
)
def test_direct_service_calls_require_draft_permissions(
    user_factory: object, service: str, permission_codename: str
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _create(actor, case)
    group = actor.groups.get(name="Administrator")
    group.permissions.remove(Permission.objects.get(codename=permission_codename))
    actor = User.objects.get(pk=actor.pk)

    with pytest.raises(PermissionDenied):
        if service == "create":
            _create(actor, case)
        else:
            get_document_draft(
                actor=actor,
                draft_id=draft.pk,
                correlation_id="draft-read-denied",
            )


def test_update_requires_change_permission(user_factory: object) -> None:
    actor = _actor(user_factory)
    draft = _create(actor, _case(actor))
    group = actor.groups.get(name="Administrator")
    group.permissions.remove(Permission.objects.get(codename="change_document_drafts"))
    actor = User.objects.get(pk=actor.pk)

    with pytest.raises(PermissionDenied):
        update_document_draft(
            actor=actor,
            draft_id=draft.pk,
            type_key=draft.type_key,
            schema_version=draft.schema_version,
            expected_revision=1,
            payload={"title": "Denied"},
            state=DocumentDraft.State.DRAFT,
            correlation_id="draft-change-denied",
        )


def test_exact_validation_boundary_is_reusable(user_factory: object) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    validated = validate_document_draft_payload(
        case=case,
        type_key="synthetic-platform-test",
        schema_version="v1",
        payload={"title": "Reusable boundary"},
    )
    assert validated.payload == {
        "notes": "",
        "participant_id": None,
        "title": "Reusable boundary",
    }
    with pytest.raises(DraftValidationError):
        validate_document_draft_payload(
            case=case,
            type_key="synthetic-platform-test",
            schema_version="v1",
            payload={"notes": "missing required title"},
        )


def test_registry_form_and_formsets_are_resolved_and_normalized(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MainForm(forms.Form):
        title = forms.CharField(max_length=50)

    class ItemForm(forms.Form):
        description = forms.CharField(max_length=50)
        participant_id = forms.UUIDField(required=False)

    item_formset = forms.formset_factory(ItemForm, extra=0, min_num=1, validate_min=True)
    typed_item_formset = cast(Any, item_formset)
    registration = replace(
        document_registry.get("synthetic-platform-test"),
        form_provider=lambda: DocumentFormBundle(MainForm, (typed_item_formset,)),
        related_fields=(
            RelatedFieldDefinition(
                "participant_id",
                RelatedObjectKind.CASE_PARTICIPANT,
                formset_prefix="form",
            ),
        ),
    )
    monkeypatch.setattr(document_registry, "get", lambda _key: registration)
    actor = _actor(user_factory)
    case = _case(actor)
    participant = cast(CaseParticipant, CaseParticipantFactory(case=case))

    validated = validate_document_draft_payload(
        case=case,
        type_key=registration.key,
        schema_version=registration.schema_version,
        payload={
            "title": "Formset contract",
            "form": [
                {
                    "description": "Dòng lặp",
                    "participant_id": str(participant.pk),
                }
            ],
        },
    )

    assert validated.payload == {
        "form": [
            {
                "description": "Dòng lặp",
                "participant_id": str(participant.pk),
            }
        ],
        "title": "Formset contract",
    }
    with pytest.raises(DraftValidationError) as unknown_error:
        validate_document_draft_payload(
            case=case,
            type_key=registration.key,
            schema_version=registration.schema_version,
            payload={"title": "Unknown row", "form": [{"unknown": "ignored?"}]},
        )
    assert unknown_error.value.invalid_fields == ("form",)
    with pytest.raises(DraftValidationError) as minimum_error:
        validate_document_draft_payload(
            case=case,
            type_key=registration.key,
            schema_version=registration.schema_version,
            payload={"title": "Missing required repeated row", "form": []},
        )
    assert minimum_error.value.invalid_fields == ("form",)
    other = cast(CaseParticipant, CaseParticipantFactory())
    with pytest.raises(DraftValidationError):
        validate_document_draft_payload(
            case=case,
            type_key=registration.key,
            schema_version=registration.schema_version,
            payload={
                "title": "Cross-case row",
                "form": [
                    {
                        "description": "Related row",
                        "participant_id": str(other.pk),
                    }
                ],
            },
        )


def test_registry_provider_and_validation_run_before_every_write(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    registration = document_registry.get("synthetic-platform-test")
    calls = 0

    def counted_provider() -> DocumentFormBundle:
        nonlocal calls
        calls += 1
        return registration.form_provider()

    monkeypatch.setattr(
        document_registry,
        "get",
        lambda _key: replace(registration, form_provider=counted_provider),
    )
    draft = _create(actor, case)
    update_document_draft(
        actor=actor,
        draft_id=draft.pk,
        type_key=draft.type_key,
        schema_version=draft.schema_version,
        expected_revision=1,
        payload=draft.payload,
        state=DocumentDraft.State.READY,
        correlation_id="draft-counted-ready",
    )

    assert calls == 2


def test_large_schema_audit_uses_bounded_field_categories(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    registration = document_registry.get("synthetic-platform-test")
    field_names = tuple(f"field_{index}" for index in range(51))
    large_form = type(
        "LargeSyntheticDraftForm",
        (forms.Form,),
        {name: forms.CharField(max_length=20) for name in field_names},
    )
    monkeypatch.setattr(
        document_registry,
        "get",
        lambda _key: replace(
            registration,
            form_provider=lambda: DocumentFormBundle(large_form),
            related_fields=(),
        ),
    )

    draft = _create(
        actor,
        _case(actor),
        payload={name: "Synthetic" for name in field_names},
    )

    event = AuditEvent.objects.get(
        action=AuditAction.DOCUMENT_DRAFT_CREATED,
        target_id=str(draft.pk),
    )
    assert event.changed_fields == ["document_fields", "state", "revision"]


def test_failed_validation_cannot_partially_update_or_mark_ready(user_factory: object) -> None:
    actor = _actor(user_factory)
    draft = _create(actor, _case(actor))

    with pytest.raises(DraftValidationError):
        update_document_draft(
            actor=actor,
            draft_id=draft.pk,
            type_key=draft.type_key,
            schema_version=draft.schema_version,
            expected_revision=1,
            payload={"notes": "Missing title"},
            state=DocumentDraft.State.READY,
            correlation_id="draft-invalid-ready",
        )

    draft.refresh_from_db()
    assert draft.revision == 1
    assert draft.state == DocumentDraft.State.DRAFT


def test_update_rejects_incompatible_schema_identity(user_factory: object) -> None:
    actor = _actor(user_factory)
    draft = _create(actor, _case(actor))

    with pytest.raises(DraftSchemaMismatch):
        update_document_draft(
            actor=actor,
            draft_id=draft.pk,
            type_key=draft.type_key,
            schema_version="v2",
            expected_revision=1,
            payload=draft.payload,
            state=draft.state,
            correlation_id="draft-update-schema-mismatch",
        )


def test_disabled_type_keeps_existing_schema_reader_but_blocks_new_drafts(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    draft = _create(actor, _case(actor))
    registration = document_registry.get(draft.type_key)
    monkeypatch.setattr(
        document_registry,
        "get",
        lambda _key: replace(registration, enabled=False),
    )

    assert (
        get_document_draft(
            actor=actor,
            draft_id=draft.pk,
            correlation_id="draft-disabled-read",
        ).pk
        == draft.pk
    )
    updated = update_document_draft(
        actor=actor,
        draft_id=draft.pk,
        type_key=draft.type_key,
        schema_version=draft.schema_version,
        expected_revision=1,
        payload={"title": "Historical schema remains readable"},
        state=DocumentDraft.State.DRAFT,
        correlation_id="draft-disabled-update",
    )
    assert updated.revision == 2
    with pytest.raises(DraftSchemaMismatch):
        _create(actor, _case(actor))


def test_create_and_update_roll_back_when_audit_fails(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    monkeypatch.setattr(
        "apps.documents.draft_services.record_audit_event",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic audit failure")),
    )
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        _create(actor, case)
    assert DocumentDraft.objects.count() == 0

    monkeypatch.undo()
    draft = _create(actor, case)
    monkeypatch.setattr(
        "apps.documents.draft_services.record_audit_event",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic audit failure")),
    )
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        update_document_draft(
            actor=actor,
            draft_id=draft.pk,
            type_key=draft.type_key,
            schema_version=draft.schema_version,
            expected_revision=1,
            payload={"title": "Must roll back"},
            state=DocumentDraft.State.READY,
            correlation_id="draft-update-audit-failure",
        )
    draft.refresh_from_db()
    assert draft.revision == 1
    assert draft.state == DocumentDraft.State.DRAFT


def test_stored_synthetic_payload_contains_only_approved_fields(user_factory: object) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    participant = cast(CaseParticipant, CaseParticipantFactory(case=case))
    draft = _create(
        actor,
        case,
        payload={
            "title": "Synthetic inspection",
            "notes": "No real case data",
            "participant_id": str(participant.pk),
        },
    )

    assert set(draft.payload) == {"title", "notes", "participant_id"}
    serialized = str(draft.payload)
    assert case.internal_reference not in serialized
    assert case.matter_type not in serialized
    assert not {"case", "court", "participants", "rendered_context", "snapshot"} & set(
        draft.payload
    )


def test_validation_does_not_log_payload_or_case_data(
    user_factory: object, caplog: pytest.LogCaptureFixture
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    sensitive_marker = "SYNTHETIC-PERSONAL-PAYLOAD-MARKER"

    with pytest.raises(DraftValidationError):
        _create(
            actor,
            case,
            payload={"notes": sensitive_marker},
        )

    assert sensitive_marker not in caplog.text
    assert case.internal_reference not in caplog.text
    assert case.matter_type not in caplog.text


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_updates_have_no_lost_write(
    user_factory: Callable[..., User], monkeypatch: pytest.MonkeyPatch
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL concurrency profile.")
    actor = _actor(user_factory)
    draft = _create(actor, _case(actor))
    barrier = Barrier(2)
    from apps.documents import draft_services

    optimistic_update = draft_services._optimistic_update

    def synchronized_update(*args: Any, **kwargs: Any) -> int:
        barrier.wait()
        return optimistic_update(*args, **kwargs)

    monkeypatch.setattr(draft_services, "_optimistic_update", synchronized_update)

    def submit(title: str) -> str:
        close_old_connections()
        thread_actor = User.objects.get(pk=actor.pk)
        try:
            try:
                update_document_draft(
                    actor=thread_actor,
                    draft_id=draft.pk,
                    type_key=draft.type_key,
                    schema_version=draft.schema_version,
                    expected_revision=1,
                    payload={"title": title},
                    state=DocumentDraft.State.DRAFT,
                    correlation_id=f"draft-race-{title[-1]}",
                )
            except DraftRevisionConflict:
                return "conflict"
            return "success"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, ("Concurrent A", "Concurrent B")))

    assert sorted(outcomes) == ["conflict", "success"]
    draft.refresh_from_db()
    assert draft.revision == 2
    assert draft.payload["title"] in {"Concurrent A", "Concurrent B"}
