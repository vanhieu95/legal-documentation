from __future__ import annotations

from collections.abc import Sequence

from django.contrib.auth.models import User

from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.recorder import AuditTarget, record_audit_event


def record_reference_success(
    *,
    actor: User,
    action: AuditAction,
    target_type: str,
    target_id: str,
    correlation_id: str,
    changed_fields: Sequence[str],
) -> None:
    record_audit_event(
        action=action,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=target_type, id=target_id),
        correlation_id=correlation_id,
        changed_fields=sorted(changed_fields),
    )


def record_reference_validation_failure(
    *,
    actor: User,
    action: AuditAction,
    reference_type: str,
    correlation_id: str,
) -> None:
    record_audit_event(
        action=action,
        outcome=AuditOutcome.FAILURE,
        actor=actor,
        target=AuditTarget(type="application"),
        correlation_id=correlation_id,
        metadata={"reason_code": "validation_error", "reference_type": reference_type},
    )


def record_case_success(
    *,
    actor: User,
    action: AuditAction,
    target_id: str,
    correlation_id: str,
    changed_fields: Sequence[str] = (),
) -> None:
    record_audit_event(
        action=action,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.CASE, id=target_id),
        correlation_id=correlation_id,
        changed_fields=sorted(changed_fields),
    )


def record_case_failure(
    *, actor: User, action: AuditAction, correlation_id: str, reason_code: str
) -> None:
    record_audit_event(
        action=action,
        outcome=AuditOutcome.FAILURE,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.APPLICATION),
        correlation_id=correlation_id,
        metadata={"reason_code": reason_code},
    )
