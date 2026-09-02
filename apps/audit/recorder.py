from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from django.contrib.auth.models import User

from apps.audit.actions import AuditAction, AuditOutcome
from apps.audit.models import AuditEvent

MAX_CHANGED_FIELDS = 50
MAX_CHANGED_FIELD_NAME_LENGTH = 64
MAX_METADATA_BYTES = 2048
MAX_METADATA_COLLECTION_SIZE = 20
MAX_METADATA_NESTING_DEPTH = 3
MAX_METADATA_STRING_LENGTH = 256
CHANGED_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

PROHIBITED_METADATA_KEYS = frozenset(
    {
        "address",
        "addresses",
        "api_key",
        "authorization",
        "body",
        "bytes",
        "content",
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "csrf",
        "csrf_token",
        "data",
        "draft",
        "exception",
        "exception_message",
        "file",
        "form",
        "header",
        "headers",
        "identity_document",
        "ip",
        "ip_address",
        "password",
        "passwords",
        "payload",
        "post",
        "request",
        "secret",
        "session",
        "session_key",
        "sessionid",
        "snapshot",
        "stack_trace",
        "token",
        "tokens",
        "traceback",
        "user_agent",
        "username",
    }
)


class AuditRecorderError(ValueError):
    """Raised when audit input violates the recorder contract."""


@dataclass(frozen=True, slots=True)
class AuditTarget:
    """Generic target reference accepted by the audit recorder."""

    type: str
    id: str = ""

    def __post_init__(self) -> None:
        if not self.type or len(self.type) > 64:
            raise AuditRecorderError("Target type must be a bounded non-empty string.")
        if len(self.id) > 128:
            raise AuditRecorderError("Target identifier exceeds the allowed length.")


def _normalize_key(key: object) -> str:
    if not isinstance(key, str):
        raise AuditRecorderError("Metadata keys must be strings.")
    normalized = key.strip().lower()
    if not normalized:
        raise AuditRecorderError("Metadata keys must be non-empty.")
    if normalized in PROHIBITED_METADATA_KEYS:
        raise AuditRecorderError(f"Metadata key '{key}' is prohibited.")
    return normalized


def _validate_metadata_value(value: object, *, depth: int) -> object:
    if isinstance(value, Mapping):
        if depth >= MAX_METADATA_NESTING_DEPTH:
            raise AuditRecorderError("Metadata nesting exceeds the allowed depth.")
        if len(value) > MAX_METADATA_COLLECTION_SIZE:
            raise AuditRecorderError("Metadata object size exceeds the allowed limit.")
        return {
            _normalize_key(key): _validate_metadata_value(nested, depth=depth + 1)
            for key, nested in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if depth >= MAX_METADATA_NESTING_DEPTH:
            raise AuditRecorderError("Metadata nesting exceeds the allowed depth.")
        if len(value) > MAX_METADATA_COLLECTION_SIZE:
            raise AuditRecorderError("Metadata collection size exceeds the allowed limit.")
        return [_validate_metadata_value(item, depth=depth + 1) for item in value]
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        if len(value) > MAX_METADATA_STRING_LENGTH:
            raise AuditRecorderError("Metadata string values exceed the allowed length.")
        return value
    raise AuditRecorderError(
        "Metadata must contain only bounded JSON primitives and cannot serialize arbitrary objects."
    )


def _validate_changed_fields(changed_fields: Sequence[str]) -> list[str]:
    if len(changed_fields) > MAX_CHANGED_FIELDS:
        raise AuditRecorderError("Changed field list exceeds the allowed limit.")
    normalized: list[str] = []
    for field_name in changed_fields:
        if not isinstance(field_name, str):
            raise AuditRecorderError("Changed field names must be strings.")
        if (
            not field_name
            or len(field_name) > MAX_CHANGED_FIELD_NAME_LENGTH
            or CHANGED_FIELD_NAME_PATTERN.fullmatch(field_name) is None
        ):
            raise AuditRecorderError("Changed field names must use a bounded safe identifier.")
        normalized.append(field_name)
    return normalized


def _validate_metadata(metadata: Mapping[str, object] | None) -> dict[str, object]:
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise AuditRecorderError("Metadata must be a mapping of bounded safe values.")
    validated = _validate_metadata_value(metadata, depth=0)
    assert isinstance(validated, dict)
    encoded = json.dumps(validated, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise AuditRecorderError("Metadata exceeds the allowed serialized size.")
    return validated


def _validate_action(action: str) -> str:
    if action not in AuditAction:
        raise AuditRecorderError("Unsupported audit action.")
    return action


def _validate_outcome(outcome: str) -> str:
    if outcome not in AuditOutcome:
        raise AuditRecorderError("Unsupported audit outcome.")
    return outcome


def _validate_correlation_id(correlation_id: str) -> str:
    if not correlation_id or len(correlation_id) > 128:
        raise AuditRecorderError("Correlation ID must be a bounded non-empty string.")
    return correlation_id


def record_audit_event(
    *,
    action: str,
    outcome: str,
    target: AuditTarget,
    correlation_id: str,
    actor: User | None = None,
    is_system_actor: bool = False,
    changed_fields: Sequence[str] | None = None,
    metadata: Mapping[str, object] | None = None,
) -> AuditEvent:
    """Record exactly one append-only audit event within the current database transaction.

    The event is created through the ORM in the active transaction. If the surrounding
    transaction rolls back, the audit row is rolled back with it. Callers must pass explicit
    action, outcome, actor or system marker, target reference, correlation ID, changed field
    names, and bounded metadata. The recorder never serializes requests, models, or exceptions.
    """
    if actor is not None and is_system_actor:
        raise AuditRecorderError("Actor and system marker cannot both be set.")
    if actor is None and not is_system_actor:
        raise AuditRecorderError("Either an actor or the system marker must be provided.")

    validated_action = _validate_action(action)
    validated_outcome = _validate_outcome(outcome)
    validated_correlation_id = _validate_correlation_id(correlation_id)
    validated_changed_fields = _validate_changed_fields(tuple(changed_fields or ()))
    validated_metadata = _validate_metadata(metadata)

    event = AuditEvent(
        actor=actor,
        is_system_actor=is_system_actor,
        action=validated_action,
        target_type=target.type,
        target_id=target.id,
        outcome=validated_outcome,
        correlation_id=validated_correlation_id,
        changed_fields=validated_changed_fields,
        metadata=validated_metadata,
    )
    event.save()
    return event
