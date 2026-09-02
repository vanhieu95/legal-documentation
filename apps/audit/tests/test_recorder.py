from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.models import AuditEvent, ImmutableAuditEventError
from apps.audit.recorder import (
    AuditRecorderError,
    AuditTarget,
    record_audit_event,
)


@pytest.fixture
def actor(user_factory: Callable[..., User]) -> User:
    return user_factory(username="synthetic-audit-actor")


@pytest.mark.django_db
def test_record_audit_event_creates_user_actor_event(actor: User) -> None:
    event = record_audit_event(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id="synthetic-correlation-001",
        changed_fields=["is_active"],
        metadata={"reason_code": "authenticated"},
    )

    assert AuditEvent.objects.count() == 1
    assert event.actor == actor
    assert event.is_system_actor is False
    assert event.action == AuditAction.IDENTITY_LOGIN
    assert event.outcome == AuditOutcome.SUCCESS
    assert event.target_type == AuditTargetType.USER
    assert event.target_id == str(actor.pk)
    assert event.correlation_id == "synthetic-correlation-001"
    assert event.changed_fields == ["is_active"]
    assert event.metadata == {"reason_code": "authenticated"}


@pytest.mark.django_db
def test_record_audit_event_creates_system_actor_event() -> None:
    event = record_audit_event(
        action=AuditAction.IDENTITY_SESSION_EXPIRED,
        outcome=AuditOutcome.SUCCESS,
        is_system_actor=True,
        target=AuditTarget(type=AuditTargetType.SESSION, id="synthetic-session"),
        correlation_id="synthetic-correlation-002",
        metadata={"reason_code": "inactivity"},
    )

    assert event.actor is None
    assert event.is_system_actor is True


@pytest.mark.django_db
def test_occurred_at_is_timezone_aware_and_stored_in_utc(actor: User) -> None:
    before = timezone.now()
    event = record_audit_event(
        action=AuditAction.IDENTITY_LOGOUT,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id="synthetic-correlation-003",
    )
    after = timezone.now()

    assert timezone.is_aware(event.occurred_at)
    assert event.occurred_at.tzinfo == UTC
    assert before <= event.occurred_at <= after


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("action", "outcome"),
    [
        (AuditAction.IDENTITY_LOGIN, AuditOutcome.SUCCESS),
        (AuditAction.IDENTITY_ACCESS_DENIED, AuditOutcome.DENIED),
    ],
)
def test_recorder_validates_stable_action_and_outcome(
    actor: User, action: str, outcome: str
) -> None:
    event = record_audit_event(
        action=action,
        outcome=outcome,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.APPLICATION),
        correlation_id="synthetic-correlation-004",
    )
    assert event.action == action
    assert event.outcome == outcome


@pytest.mark.django_db
def test_recorder_rejects_unknown_action(actor: User) -> None:
    with pytest.raises(AuditRecorderError, match="Unsupported audit action"):
        record_audit_event(
            action="identity.unknown",
            outcome=AuditOutcome.SUCCESS,
            actor=actor,
            target=AuditTarget(type=AuditTargetType.APPLICATION),
            correlation_id="synthetic-correlation-005",
        )


@pytest.mark.django_db
def test_recorder_rejects_unknown_outcome(actor: User) -> None:
    with pytest.raises(AuditRecorderError, match="Unsupported audit outcome"):
        record_audit_event(
            action=AuditAction.IDENTITY_LOGIN,
            outcome="maybe",
            actor=actor,
            target=AuditTarget(type=AuditTargetType.APPLICATION),
            correlation_id="synthetic-correlation-006",
        )


@pytest.mark.django_db
def test_recorder_rejects_prohibited_metadata_keys(actor: User) -> None:
    with pytest.raises(AuditRecorderError, match="prohibited"):
        record_audit_event(
            action=AuditAction.IDENTITY_LOGIN,
            outcome=AuditOutcome.FAILURE,
            is_system_actor=True,
            target=AuditTarget(type=AuditTargetType.APPLICATION),
            correlation_id="synthetic-correlation-007",
            metadata={"password": "secret"},
        )


@pytest.mark.django_db
def test_recorder_rejects_excessive_metadata_size(actor: User) -> None:
    metadata = {f"field_{index:02d}": "x" * 120 for index in range(20)}
    with pytest.raises(AuditRecorderError, match="serialized size"):
        record_audit_event(
            action=AuditAction.IDENTITY_LOGIN,
            outcome=AuditOutcome.FAILURE,
            is_system_actor=True,
            target=AuditTarget(type=AuditTargetType.APPLICATION),
            correlation_id="synthetic-correlation-008",
            metadata=metadata,
        )


@pytest.mark.django_db
def test_recorder_rejects_excessive_metadata_nesting(actor: User) -> None:
    metadata: dict[str, object] = {
        "level1": {"level2": {"level3": {"level4": {"too_deep": "value"}}}}
    }
    with pytest.raises(AuditRecorderError, match="nesting"):
        record_audit_event(
            action=AuditAction.IDENTITY_LOGIN,
            outcome=AuditOutcome.FAILURE,
            is_system_actor=True,
            target=AuditTarget(type=AuditTargetType.APPLICATION),
            correlation_id="synthetic-correlation-009",
            metadata=metadata,
        )


@pytest.mark.django_db
def test_recorder_rejects_excessive_metadata_collection_size(actor: User) -> None:
    with pytest.raises(AuditRecorderError, match="collection size"):
        record_audit_event(
            action=AuditAction.IDENTITY_LOGIN,
            outcome=AuditOutcome.FAILURE,
            is_system_actor=True,
            target=AuditTarget(type=AuditTargetType.APPLICATION),
            correlation_id="synthetic-correlation-010",
            metadata={"items": list(range(25))},
        )


@pytest.mark.django_db
def test_recorder_rejects_request_like_metadata(actor: User) -> None:
    with pytest.raises(AuditRecorderError, match="prohibited"):
        record_audit_event(
            action=AuditAction.IDENTITY_LOGIN,
            outcome=AuditOutcome.FAILURE,
            is_system_actor=True,
            target=AuditTarget(type=AuditTargetType.APPLICATION),
            correlation_id="synthetic-correlation-011",
            metadata={"request": {"body": "unsafe"}},
        )


@pytest.mark.django_db
def test_recorder_rejects_arbitrary_object_metadata(actor: User) -> None:
    with pytest.raises(AuditRecorderError, match="arbitrary objects"):
        record_audit_event(
            action=AuditAction.IDENTITY_LOGIN,
            outcome=AuditOutcome.FAILURE,
            is_system_actor=True,
            target=AuditTarget(type=AuditTargetType.APPLICATION),
            correlation_id="synthetic-correlation-012",
            metadata={"actor": actor},
        )


@pytest.mark.django_db
def test_recorder_creates_exactly_one_event_per_call(actor: User) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id="synthetic-correlation-013",
    )
    assert AuditEvent.objects.count() == 1


@pytest.mark.django_db
def test_recorder_commits_with_outer_transaction(actor: User) -> None:
    with transaction.atomic():
        record_audit_event(
            action=AuditAction.IDENTITY_LOGIN,
            outcome=AuditOutcome.SUCCESS,
            actor=actor,
            target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
            correlation_id="synthetic-correlation-014",
        )
    assert AuditEvent.objects.count() == 1


@pytest.mark.django_db
def test_recorder_rolls_back_with_outer_transaction(actor: User) -> None:
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            record_audit_event(
                action=AuditAction.IDENTITY_LOGIN,
                outcome=AuditOutcome.SUCCESS,
                actor=actor,
                target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
                correlation_id="synthetic-correlation-015",
            )
            raise IntegrityError("synthetic rollback")
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_audit_event_instance_update_is_rejected(actor: User) -> None:
    event = record_audit_event(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id="synthetic-correlation-016",
    )
    event.outcome = AuditOutcome.FAILURE
    with pytest.raises(ImmutableAuditEventError):
        event.save()


@pytest.mark.django_db
def test_audit_event_queryset_update_is_rejected(actor: User) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id="synthetic-correlation-017",
    )
    with pytest.raises(ImmutableAuditEventError):
        AuditEvent.objects.update(outcome=AuditOutcome.FAILURE)


@pytest.mark.django_db
def test_audit_event_instance_delete_is_rejected(actor: User) -> None:
    event = record_audit_event(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id="synthetic-correlation-018",
    )
    with pytest.raises(ImmutableAuditEventError):
        event.delete()


@pytest.mark.django_db
def test_audit_event_queryset_delete_is_rejected(actor: User) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id="synthetic-correlation-019",
    )
    with pytest.raises(ImmutableAuditEventError):
        AuditEvent.objects.all().delete()


@pytest.mark.django_db
def test_recorder_rejects_actor_and_system_marker_together(actor: User) -> None:
    with pytest.raises(AuditRecorderError, match="cannot both be set"):
        record_audit_event(
            action=AuditAction.IDENTITY_LOGIN,
            outcome=AuditOutcome.SUCCESS,
            actor=actor,
            is_system_actor=True,
            target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
            correlation_id="synthetic-correlation-020",
        )


@pytest.mark.django_db
def test_recorder_requires_actor_or_system_marker(actor: User) -> None:
    with pytest.raises(AuditRecorderError, match="system marker"):
        record_audit_event(
            action=AuditAction.IDENTITY_LOGIN,
            outcome=AuditOutcome.SUCCESS,
            target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
            correlation_id="synthetic-correlation-021",
        )


@pytest.mark.django_db
def test_allowed_bounded_metadata_is_stored(actor: User) -> None:
    metadata = {
        "reason_code": "authenticated",
        "nested": {"count": 1, "flags": [True, False]},
    }
    event = record_audit_event(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id="synthetic-correlation-022",
        metadata=metadata,
    )
    assert event.metadata == metadata
    assert len(json.dumps(event.metadata)) <= 2048
