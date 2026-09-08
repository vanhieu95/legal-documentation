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
    REFERENCE_COURT_CREATED = "reference.court_created"
    REFERENCE_COURT_UPDATED = "reference.court_updated"
    REFERENCE_COURT_DEACTIVATED = "reference.court_deactivated"
    REFERENCE_ENTITY_CREATED = "reference.entity_created"
    REFERENCE_ENTITY_UPDATED = "reference.entity_updated"
    REFERENCE_ENTITY_DEACTIVATED = "reference.entity_deactivated"
    REFERENCE_ADDRESS_CREATED = "reference.address_created"
    REFERENCE_ADDRESS_UPDATED = "reference.address_updated"
    REFERENCE_ADDRESS_DEACTIVATED = "reference.address_deactivated"
    REFERENCE_OFFICIAL_CREATED = "reference.official_created"
    REFERENCE_OFFICIAL_UPDATED = "reference.official_updated"
    REFERENCE_OFFICIAL_DEACTIVATED = "reference.official_deactivated"
    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"


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
    COURT = "court"
    ENTITY = "entity"
    ENTITY_ADDRESS = "entity_address"
    OFFICIAL = "official"
    CASE = "case"
