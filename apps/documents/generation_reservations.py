from __future__ import annotations

import hashlib
import math
import re
import secrets
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction

from apps.accounts.policies import (
    ApplicationPermission,
    application_access_policy,
    service_permission_required,
)
from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.recorder import AuditTarget, record_audit_event
from apps.cases.document_prefill import authorize_document_case, document_case_transfer
from apps.cases.models import CaseRecord
from apps.cases.policies import can_generate_documents_for_case, case_object_policy
from apps.core.correlation import generate_correlation_id, normalize_correlation_id
from apps.documents.draft_services import DraftValidationError, validate_document_draft_payload
from apps.documents.models import DocumentDraft, GeneratedDocument, TemplateVersion
from apps.documents.prefill import PrefillSource, map_case_transfer
from apps.documents.registry import DocumentRegistration, UnknownDocumentTypeKey, document_registry
from apps.documents.template_locks import acquire_template_type_lock

_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class InvalidIdempotencyKey(ValueError):
    """The submitted reservation token is not an application-issued token shape."""


class GenerationReservationConflict(ValueError):
    """Confirmed case, draft, template, or idempotency facts no longer match."""

    status_code = 409


class GenerationReservationUnavailable(ValueError):
    """The deployed type, exact draft schema, or active template is unavailable."""


def issue_generation_idempotency_key() -> str:
    """Issue 256 bits of opaque randomness in a bounded URL-safe representation."""
    return secrets.token_urlsafe(32)


def _idempotency_hash(value: str) -> str:
    if not isinstance(value, str) or _IDEMPOTENCY_KEY_PATTERN.fullmatch(value) is None:
        raise InvalidIdempotencyKey("The generation idempotency key is invalid.")
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _json_value(value: object) -> object:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GenerationReservationUnavailable("The validated value cannot be snapshotted.")
        return value
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise GenerationReservationUnavailable("Snapshot field names must be strings.")
        return {key: _json_value(nested) for key, nested in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    raise GenerationReservationUnavailable("The validated value cannot be snapshotted.")


def _accessible_locked_case(*, actor: User, case_id: UUID) -> CaseRecord:
    application_access_policy.require_permission(actor, ApplicationPermission.VIEW_CASES)
    queryset = case_object_policy.scope_queryset(
        actor,
        CaseRecord.objects.select_for_update(),
    )
    try:
        return queryset.get(pk=case_id)
    except CaseRecord.DoesNotExist as error:
        raise PermissionDenied from error


def _existing_attempt(
    *,
    actor: User,
    idempotency_hash: str,
    case_id: UUID,
    draft_id: UUID,
    type_key: str,
    schema_version: str,
) -> GeneratedDocument | None:
    attempt = GeneratedDocument.objects.filter(
        actor=actor, idempotency_key_hash=idempotency_hash
    ).first()
    if attempt is None:
        return None
    if (
        attempt.case_id != case_id
        or attempt.source_draft_id != draft_id
        or attempt.type_key != type_key
        or attempt.schema_version != schema_version
    ):
        raise GenerationReservationConflict(
            "The idempotency key belongs to a different generation request."
        )
    return attempt


def _registration(type_key: str, schema_version: str) -> DocumentRegistration:
    try:
        registration = document_registry.get(type_key)
    except UnknownDocumentTypeKey as error:
        raise GenerationReservationUnavailable("The document type is unavailable.") from error
    if not registration.enabled or registration.schema_version != schema_version:
        raise GenerationReservationUnavailable("The document type is unavailable.")
    return registration


def _active_template(*, type_key: str, expected_template_id: UUID) -> TemplateVersion:
    acquire_template_type_lock(type_key)
    try:
        template = TemplateVersion.objects.select_for_update().get(
            type_key=type_key,
            status=TemplateVersion.Status.ACTIVE,
        )
    except TemplateVersion.DoesNotExist as error:
        raise GenerationReservationUnavailable("No active template is available.") from error
    if template.pk != expected_template_id:
        raise GenerationReservationConflict("The active template changed.")
    if template.validation_report.get("result") != "valid":
        raise GenerationReservationUnavailable("The active template is invalid.")
    return template


def _snapshot_prefill(
    *,
    registration: DocumentRegistration,
    actor: User,
    case_id: UUID,
    payload: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    transfer = document_case_transfer(authorize_document_case(actor=actor, case_id=case_id))
    prefill = map_case_transfer(
        registration=registration,
        transfer=transfer,
        draft_payload=payload,
    )
    resolved: dict[str, object] = {}
    for name, provenance in prefill.sources.items():
        if provenance.source is PrefillSource.DOCUMENT or name not in prefill.form_initial:
            continue
        comparison = prefill.overrides.get(name)
        value = comparison.case_value if comparison is not None else prefill.form_initial[name]
        resolved[name] = _json_value(value)
    overrides: dict[str, object] = {}
    for name, comparison in prefill.overrides.items():
        case_value = _json_value(comparison.case_value)
        draft_value = _json_value(comparison.draft_value)
        if case_value != draft_value:
            overrides[name] = {
                "case_value": case_value,
                "draft_value": draft_value,
                "source": prefill.sources[name].source.value,
            }
    return resolved, overrides


def _contains_sensitive_value(value: object, candidate: str) -> bool:
    if isinstance(value, str):
        return value == candidate
    if isinstance(value, Mapping):
        return any(_contains_sensitive_value(nested, candidate) for nested in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_sensitive_value(nested, candidate) for nested in value)
    return False


def _safe_audit_correlation_id(
    *, candidate: str, attempt: GeneratedDocument, idempotency_key: str
) -> str:
    normalized = normalize_correlation_id(candidate)
    sensitive_values: tuple[object, ...] = (
        idempotency_key,
        str(attempt.case_id),
        str(attempt.source_draft_id),
        attempt.input_snapshot,
        attempt.resolved_values_snapshot,
        attempt.override_snapshot,
    )
    if normalized is None or any(
        _contains_sensitive_value(value, normalized) for value in sensitive_values
    ):
        return generate_correlation_id()
    return normalized


def _audit_reservation(
    *,
    actor: User,
    attempt: GeneratedDocument,
    correlation_id: str,
    idempotency_key: str,
) -> None:
    record_audit_event(
        action=AuditAction.DOCUMENT_GENERATION_RESERVED,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.GENERATED_DOCUMENT, id=str(attempt.pk)),
        correlation_id=_safe_audit_correlation_id(
            candidate=correlation_id,
            attempt=attempt,
            idempotency_key=idempotency_key,
        ),
        changed_fields=("status",),
        metadata={
            "type_key": attempt.type_key,
            "schema_version": attempt.schema_version,
            "template_version": attempt.template_version.version,
            "case_revision": attempt.case_revision,
            "draft_revision": attempt.draft_revision,
        },
    )


@service_permission_required(ApplicationPermission.GENERATE_DOCUMENTS)
def reserve_generation(
    *,
    actor: User,
    case_id: UUID,
    draft_id: UUID,
    type_key: str,
    schema_version: str,
    expected_case_revision: int,
    expected_draft_revision: int,
    expected_template_id: UUID,
    idempotency_key: str,
    correlation_id: str,
) -> GeneratedDocument:
    """Reserve immutable generation facts; perform no rendering or storage work."""
    key_hash = _idempotency_hash(idempotency_key)
    try:
        with transaction.atomic():
            case = _accessible_locked_case(actor=actor, case_id=case_id)
            if not can_generate_documents_for_case(case):
                raise PermissionDenied
            existing = _existing_attempt(
                actor=actor,
                idempotency_hash=key_hash,
                case_id=case_id,
                draft_id=draft_id,
                type_key=type_key,
                schema_version=schema_version,
            )
            if existing is not None:
                return existing
            if case.revision != expected_case_revision:
                raise GenerationReservationConflict("The case revision changed.")
            registration = _registration(type_key, schema_version)
            try:
                draft = DocumentDraft.objects.select_for_update().get(
                    pk=draft_id,
                    case=case,
                    type_key=type_key,
                    schema_version=schema_version,
                )
            except DocumentDraft.DoesNotExist as error:
                raise GenerationReservationUnavailable("The draft is unavailable.") from error
            if draft.revision != expected_draft_revision:
                raise GenerationReservationConflict("The draft revision changed.")
            if draft.state != DocumentDraft.State.READY:
                raise GenerationReservationUnavailable("The draft is not ready.")
            try:
                validated = validate_document_draft_payload(
                    case=case,
                    type_key=type_key,
                    schema_version=schema_version,
                    payload=draft.payload,
                )
            except DraftValidationError as error:
                raise GenerationReservationUnavailable("The draft is invalid.") from error
            template = _active_template(
                type_key=type_key, expected_template_id=expected_template_id
            )
            resolved, overrides = _snapshot_prefill(
                registration=registration,
                actor=actor,
                case_id=case.pk,
                payload=validated.payload,
            )
            attempt = GeneratedDocument(
                case=case,
                type_key=type_key,
                template_version=template,
                schema_version=schema_version,
                source_draft_id=draft.pk,
                case_revision=case.revision,
                draft_revision=draft.revision,
                input_snapshot={"version": 1, "values": validated.payload},
                resolved_values_snapshot={"version": 1, "values": resolved},
                override_snapshot={"version": 1, "values": overrides},
                template_snapshot={
                    "version": 1,
                    "identity": {
                        "id": str(template.pk),
                        "type_key": template.type_key,
                        "version": template.version,
                        "checksum_sha256": template.checksum_sha256,
                    },
                },
                actor=actor,
                idempotency_key_hash=key_hash,
            )
            attempt.save()
            _audit_reservation(
                actor=actor,
                attempt=attempt,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
            return attempt
    except IntegrityError:
        existing = _existing_attempt(
            actor=actor,
            idempotency_hash=key_hash,
            case_id=case_id,
            draft_id=draft_id,
            type_key=type_key,
            schema_version=schema_version,
        )
        if existing is not None:
            return existing
        raise GenerationReservationConflict("The generation reservation conflicted.") from None
