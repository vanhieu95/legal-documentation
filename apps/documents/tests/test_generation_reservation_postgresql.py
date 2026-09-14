from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from time import sleep
from uuid import UUID

import pytest
from django.contrib.auth.models import User
from django.db import DatabaseError, close_old_connections, connection
from django.db.models import F

from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.cases.models import CaseRecord
from apps.documents import draft_services, generation_reservations
from apps.documents.draft_services import update_document_draft
from apps.documents.generation_reservations import (
    GenerationReservationConflict,
    issue_generation_idempotency_key,
    reserve_generation,
)
from apps.documents.models import DocumentDraft, GeneratedDocument, TemplateVersion
from apps.documents.registry import DocumentRegistration
from apps.documents.services import activate_template_version
from apps.documents.tests.test_generation_reservations import (
    _active_template,
    _actor,
    _case,
    _ready_draft,
)
from apps.documents.tests.test_template_versions import template_values

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db(transaction=True)]


def _require_postgresql() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL reservation races.")


def _submit(
    *,
    barrier: Barrier,
    actor_id: int,
    case_id: UUID,
    draft_id: UUID,
    template_id: UUID,
    case_revision: int,
    draft_revision: int,
    token: str,
) -> tuple[str, UUID | None]:
    close_old_connections()
    try:
        barrier.wait()
        attempt = reserve_generation(
            actor=User.objects.get(pk=actor_id),
            case_id=case_id,
            draft_id=draft_id,
            type_key="synthetic-platform-test",
            schema_version="v1",
            expected_case_revision=case_revision,
            expected_draft_revision=draft_revision,
            expected_template_id=template_id,
            idempotency_key=token,
            correlation_id="postgresql-reservation-race",
        )
        return "reserved", attempt.pk
    except GenerationReservationConflict:
        return "conflict", None
    finally:
        close_old_connections()


def _fixture(
    user_factory: object,
) -> tuple[User, CaseRecord, DocumentDraft, TemplateVersion]:
    actor = _actor(user_factory)
    case = _case(actor)
    draft = _ready_draft(actor, case)
    template = _active_template(actor)
    return actor, case, draft, template


def test_concurrent_duplicate_token_returns_one_attempt_and_one_audit(
    user_factory: object,
) -> None:
    _require_postgresql()
    actor, case, draft, template = _fixture(user_factory)
    token = issue_generation_idempotency_key()
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _index: _submit(
                    barrier=barrier,
                    actor_id=actor.pk,
                    case_id=case.pk,
                    draft_id=draft.pk,
                    template_id=template.pk,
                    case_revision=case.revision,
                    draft_revision=draft.revision,
                    token=token,
                ),
                range(2),
            )
        )

    assert results[0][0] == results[1][0] == "reserved"
    assert results[0][1] == results[1][1]
    assert GeneratedDocument.objects.count() == 1
    assert AuditEvent.objects.filter(action=AuditAction.DOCUMENT_GENERATION_RESERVED).count() == 1


def test_concurrent_distinct_tokens_create_two_attempts(user_factory: object) -> None:
    _require_postgresql()
    actor, case, draft, template = _fixture(user_factory)
    barrier = Barrier(2)
    tokens = (issue_generation_idempotency_key(), issue_generation_idempotency_key())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda token: _submit(
                    barrier=barrier,
                    actor_id=actor.pk,
                    case_id=case.pk,
                    draft_id=draft.pk,
                    template_id=template.pk,
                    case_revision=case.revision,
                    draft_revision=draft.revision,
                    token=token,
                ),
                tokens,
            )
        )

    assert [result[0] for result in results] == ["reserved", "reserved"]
    assert results[0][1] != results[1][1]
    assert GeneratedDocument.objects.count() == 2


def test_concurrent_same_actor_token_across_cases_returns_conflict_not_validation_error(
    user_factory: object,
) -> None:
    _require_postgresql()
    actor, first_case, first_draft, template = _fixture(user_factory)
    second_case = _case(actor)
    second_draft = _ready_draft(actor, second_case)
    token = issue_generation_idempotency_key()
    barrier = Barrier(2)

    requests = (
        (first_case, first_draft),
        (second_case, second_draft),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda request: _submit(
                    barrier=barrier,
                    actor_id=actor.pk,
                    case_id=request[0].pk,
                    draft_id=request[1].pk,
                    template_id=template.pk,
                    case_revision=request[0].revision,
                    draft_revision=request[1].revision,
                    token=token,
                ),
                requests,
            )
        )

    assert sorted(result[0] for result in results) == ["conflict", "reserved"]
    assert GeneratedDocument.objects.count() == 1


def test_template_activation_race_pins_old_template_or_reports_conflict(
    user_factory: object,
) -> None:
    _require_postgresql()
    actor, case, draft, old = _fixture(user_factory)
    candidate = TemplateVersion.objects.create(
        **template_values(uploader=actor, version="generation-v2")
    )
    candidate.validation_report = {
        "schema_version": 1,
        "result": "valid",
        "categories": [],
        "counts": {"synthetic_renders": 2},
    }
    candidate.save(update_fields=("validation_report",))
    candidate.transition_to(TemplateVersion.Status.VALID)
    barrier = Barrier(2)

    def activate() -> str:
        close_old_connections()
        try:
            barrier.wait()
            activate_template_version(
                actor=User.objects.get(pk=actor.pk),
                template_id=candidate.pk,
                expected_status=TemplateVersion.Status.VALID,
                expected_active_id=old.pk,
                correlation_id="postgresql-template-race",
            )
            return "activated"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        reservation_future = pool.submit(
            _submit,
            barrier=barrier,
            actor_id=actor.pk,
            case_id=case.pk,
            draft_id=draft.pk,
            template_id=old.pk,
            case_revision=case.revision,
            draft_revision=draft.revision,
            token=issue_generation_idempotency_key(),
        )
        activation_future = pool.submit(activate)
        reservation = reservation_future.result()
        assert activation_future.result() == "activated"

    assert reservation[0] in {"reserved", "conflict"}
    if reservation[0] == "reserved":
        attempt_id = reservation[1]
        assert attempt_id is not None
        assert GeneratedDocument.objects.get(pk=attempt_id).template_version_id == old.pk


@pytest.mark.parametrize("edited", ["case", "draft"])
def test_case_and_draft_edit_races_are_consistent(user_factory: object, edited: str) -> None:
    _require_postgresql()
    actor, case, draft, template = _fixture(user_factory)
    barrier = Barrier(2)

    def edit() -> str:
        close_old_connections()
        try:
            barrier.wait()
            if edited == "case":
                type(case).objects.filter(pk=case.pk, revision=case.revision).update(
                    matter_type="Concurrent case value", revision=F("revision") + 1
                )
            else:
                DocumentDraft.objects.filter(pk=draft.pk, revision=draft.revision).update(
                    payload={**draft.payload, "title": "Concurrent draft value"},
                    revision=F("revision") + 1,
                )
            return "edited"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        reservation_future = pool.submit(
            _submit,
            barrier=barrier,
            actor_id=actor.pk,
            case_id=case.pk,
            draft_id=draft.pk,
            template_id=template.pk,
            case_revision=case.revision,
            draft_revision=draft.revision,
            token=issue_generation_idempotency_key(),
        )
        edit_future = pool.submit(edit)
        reservation = reservation_future.result()
        assert edit_future.result() == "edited"

    assert reservation[0] in {"reserved", "conflict"}
    if reservation[0] == "reserved":
        attempt_id = reservation[1]
        assert attempt_id is not None
        attempt = GeneratedDocument.objects.get(pk=attempt_id)
        assert attempt.case_revision == case.revision
        assert attempt.draft_revision == draft.revision
        assert attempt.input_snapshot["values"]["title"] == draft.payload["title"]


def test_draft_service_update_and_reservation_do_not_deadlock(
    user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_postgresql()
    actor, case, draft, template = _fixture(user_factory)
    barrier = Barrier(2)
    reservation_has_case = Event()
    draft_update_locked = Event()
    original_registration = generation_reservations._registration
    original_update = draft_services._optimistic_update

    def pause_after_case_lock(type_key: str, schema_version: str) -> DocumentRegistration:
        reservation_has_case.set()
        draft_update_locked.wait(timeout=2)
        return original_registration(type_key, schema_version)

    def expose_draft_lock(*args: object, **kwargs: object) -> int:
        result = original_update(*args, **kwargs)  # type: ignore[arg-type]
        draft_update_locked.set()
        sleep(0.2)
        return result

    monkeypatch.setattr(generation_reservations, "_registration", pause_after_case_lock)
    monkeypatch.setattr(draft_services, "_optimistic_update", expose_draft_lock)

    def reserve() -> str:
        close_old_connections()
        try:
            barrier.wait()
            _submit(
                barrier=Barrier(1),
                actor_id=actor.pk,
                case_id=case.pk,
                draft_id=draft.pk,
                template_id=template.pk,
                case_revision=case.revision,
                draft_revision=draft.revision,
                token=issue_generation_idempotency_key(),
            )
            return "reserved"
        except DatabaseError:
            return "database-error"
        finally:
            close_old_connections()

    def edit() -> str:
        close_old_connections()
        try:
            barrier.wait()
            reservation_has_case.wait(timeout=2)
            update_document_draft(
                actor=User.objects.get(pk=actor.pk),
                draft_id=draft.pk,
                type_key=draft.type_key,
                schema_version=draft.schema_version,
                expected_revision=draft.revision,
                payload={**draft.payload, "title": "Concurrent service edit"},
                state=DocumentDraft.State.READY,
                correlation_id="postgresql-draft-service-race",
            )
            return "edited"
        except DatabaseError:
            return "database-error"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        reserve_future = pool.submit(reserve)
        edit_future = pool.submit(edit)
        results = (reserve_future.result(), edit_future.result())

    assert "database-error" not in results
