from __future__ import annotations

from collections.abc import Sequence

from django.contrib.auth.models import User

from apps.audit.actions import AuditAction, AuditOutcome
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
