from __future__ import annotations

from enum import StrEnum


class AuditAction(StrEnum):
    """Stable audit action identifiers for supported workflows."""

    IDENTITY_LOGIN = "identity.login"
    IDENTITY_LOGOUT = "identity.logout"
    IDENTITY_SESSION_EXPIRED = "identity.session_expired"
    IDENTITY_ACCOUNT_ACTIVATED = "identity.account_activated"
    IDENTITY_ACCOUNT_DEACTIVATED = "identity.account_deactivated"
    IDENTITY_PASSWORD_CHANGED = "identity.password_changed"
    IDENTITY_PASSWORD_RESET = "identity.password_reset"
    IDENTITY_GROUP_CHANGED = "identity.group_changed"
    IDENTITY_PERMISSION_CHANGED = "identity.permission_changed"
    IDENTITY_ACCESS_DENIED = "identity.access_denied"


class AuditOutcome(StrEnum):
    """Stable audit outcome identifiers."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditTargetType(StrEnum):
    """Generic target categories used by the audit recorder."""

    USER = "user"
    SESSION = "session"
    GROUP = "group"
    PERMISSION = "permission"
    APPLICATION = "application"
