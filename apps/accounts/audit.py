from __future__ import annotations

from django.contrib.auth.models import Group, Permission, User
from django.http import HttpRequest

from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.recorder import AuditTarget, record_audit_event
from apps.core.correlation import get_request_correlation_id


def _safe_route_name(request: HttpRequest) -> str:
    if request.resolver_match is None:
        return ""
    return request.resolver_match.view_name or ""


def record_identity_login_success(*, request: HttpRequest, actor: User) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id=get_request_correlation_id(request),
        metadata={"route_name": _safe_route_name(request)},
    )


def record_identity_login_failure(
    *,
    request: HttpRequest,
    reason_code: str,
    outcome: AuditOutcome = AuditOutcome.FAILURE,
) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=outcome,
        is_system_actor=True,
        target=AuditTarget(type=AuditTargetType.APPLICATION),
        correlation_id=get_request_correlation_id(request),
        metadata={"reason_code": reason_code, "route_name": _safe_route_name(request)},
    )


def record_identity_logout(*, request: HttpRequest, actor: User) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_LOGOUT,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id=get_request_correlation_id(request),
        metadata={"route_name": _safe_route_name(request)},
    )


def record_identity_session_expired(
    *,
    user_id: int,
    reason_code: str,
    correlation_id: str,
) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_SESSION_EXPIRED,
        outcome=AuditOutcome.SUCCESS,
        is_system_actor=True,
        target=AuditTarget(type=AuditTargetType.SESSION, id=str(user_id)),
        correlation_id=correlation_id,
        metadata={"reason_code": reason_code},
    )


def record_identity_account_activated(*, actor: User, user: User, correlation_id: str) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_ACCOUNT_ACTIVATED,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(user.pk)),
        correlation_id=correlation_id,
        changed_fields=["is_active"],
    )


def record_identity_account_deactivated(*, actor: User, user: User, correlation_id: str) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_ACCOUNT_DEACTIVATED,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(user.pk)),
        correlation_id=correlation_id,
        changed_fields=["is_active"],
    )


def record_identity_password_changed(*, actor: User, user: User, correlation_id: str) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_PASSWORD_CHANGED,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(user.pk)),
        correlation_id=correlation_id,
        changed_fields=["password"],
    )


def record_identity_password_reset(*, user: User, correlation_id: str) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_PASSWORD_RESET,
        outcome=AuditOutcome.SUCCESS,
        is_system_actor=True,
        target=AuditTarget(type=AuditTargetType.USER, id=str(user.pk)),
        correlation_id=correlation_id,
        changed_fields=["password"],
    )


def record_identity_group_changed(
    *,
    actor: User,
    user: User,
    correlation_id: str,
    changed_fields: list[str],
) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_GROUP_CHANGED,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(user.pk)),
        correlation_id=correlation_id,
        changed_fields=changed_fields,
    )


def record_identity_permission_changed(
    *,
    actor: User,
    user: User,
    correlation_id: str,
    changed_fields: list[str],
) -> None:
    record_audit_event(
        action=AuditAction.IDENTITY_PERMISSION_CHANGED,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(user.pk)),
        correlation_id=correlation_id,
        changed_fields=changed_fields,
    )


def record_identity_access_denied(
    *,
    request: HttpRequest | None = None,
    actor: User | None = None,
    permission: str,
    correlation_id: str,
    route_name: str = "",
    is_htmx: bool = False,
) -> None:
    metadata = {
        "permission": permission,
        "route_name": route_name,
        "transport": "htmx" if is_htmx else "full_page",
    }
    if actor is not None and actor.is_authenticated:
        record_audit_event(
            action=AuditAction.IDENTITY_ACCESS_DENIED,
            outcome=AuditOutcome.DENIED,
            actor=actor,
            target=AuditTarget(type=AuditTargetType.APPLICATION),
            correlation_id=correlation_id,
            metadata=metadata,
        )
        return
    record_audit_event(
        action=AuditAction.IDENTITY_ACCESS_DENIED,
        outcome=AuditOutcome.DENIED,
        is_system_actor=True,
        target=AuditTarget(type=AuditTargetType.APPLICATION),
        correlation_id=correlation_id,
        metadata=metadata,
    )


def serialize_group_names(groups: list[Group]) -> list[str]:
    return sorted(group.name for group in groups)


def serialize_permission_codenames(permissions: list[Permission]) -> list[str]:
    return sorted(
        f"{permission.content_type.app_label}.{permission.codename}" for permission in permissions
    )
