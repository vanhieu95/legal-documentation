from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.policies import (
    ApplicationPermission,
    application_access_policy,
    service_permission_required,
)
from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.recorder import AuditTarget, record_audit_event
from apps.cases.models import CaseParticipant, CaseRecord
from apps.cases.policies import can_generate_documents_for_case, case_object_policy
from apps.documents.models import MAX_DRAFT_PAYLOAD_BYTES, DocumentDraft
from apps.documents.registry import (
    DocumentRegistration,
    RelatedObjectKind,
    UnknownDocumentTypeKey,
    document_registry,
)


class DraftSchemaMismatch(ValueError):
    """The requested code-owned schema cannot read or write this draft."""


class DraftValidationError(ValueError):
    """The payload did not satisfy its exact deployed form contract."""

    def __init__(self, invalid_fields: tuple[str, ...] = ()) -> None:
        super().__init__("The document draft payload is invalid.")
        self.invalid_fields = invalid_fields


class DraftPayloadTooLarge(DraftValidationError):
    """The serialized document-only payload exceeds its hard limit."""


class DraftRevisionConflict(ValueError):
    """A newer draft revision won the optimistic update."""

    status_code = 409


class DraftAlreadyExists(DraftRevisionConflict):
    """The case already has a draft for this type and schema."""


@dataclass(frozen=True, slots=True)
class ValidatedDraftPayload:
    payload: dict[str, object]
    field_names: tuple[str, ...]


def _registration(type_key: str, schema_version: str) -> DocumentRegistration:
    try:
        registration = document_registry.get(type_key)
    except UnknownDocumentTypeKey as error:
        raise DraftSchemaMismatch("The document type is not deployed.") from error
    if registration.schema_version != schema_version:
        raise DraftSchemaMismatch("The document schema version is incompatible.")
    return registration


def _encoded_payload_size(payload: Mapping[str, object]) -> int:
    try:
        return len(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as error:
        raise DraftValidationError() from error


def _json_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(nested) for key, nested in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


def _formset_data(
    prefix: str, rows: object, *, allowed_fields: frozenset[str]
) -> dict[str, object]:
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise DraftValidationError((prefix,))
    data: dict[str, object] = {
        f"{prefix}-TOTAL_FORMS": len(rows),
        f"{prefix}-INITIAL_FORMS": 0,
        f"{prefix}-MIN_NUM_FORMS": 0,
        f"{prefix}-MAX_NUM_FORMS": 1000,
    }
    for index, row in enumerate(rows):
        assert isinstance(row, Mapping)
        if set(row) - allowed_fields:
            raise DraftValidationError((prefix,))
        for name, value in row.items():
            data[f"{prefix}-{index}-{name}"] = value
    return data


def _validate_related_fields(
    *,
    case: CaseRecord,
    registration: DocumentRegistration,
    form: forms.Form,
    formsets: Mapping[str, forms.BaseFormSet[forms.Form]],
) -> None:
    participant_paths: list[tuple[str, UUID]] = []
    for related in registration.related_fields:
        values = (
            (form.cleaned_data.get(related.name),)
            if related.formset_prefix is None
            else tuple(
                row.get(related.name)
                for row in formsets[related.formset_prefix].cleaned_data
                if row and not row.get("DELETE")
            )
        )
        for identifier in values:
            if identifier is None:
                continue
            if related.object_kind is RelatedObjectKind.CASE_PARTICIPANT:
                participant_paths.append(
                    (
                        related.name
                        if related.formset_prefix is None
                        else f"{related.formset_prefix}.{related.name}",
                        identifier,
                    )
                )
    permitted_ids = set(
        CaseParticipant.objects.filter(
            case=case,
            pk__in={identifier for _path, identifier in participant_paths},
        ).values_list("pk", flat=True)
    )
    invalid = [path for path, identifier in participant_paths if identifier not in permitted_ids]
    if invalid:
        raise DraftValidationError(tuple(sorted(invalid)))


def validate_document_draft_payload(
    *,
    case: CaseRecord,
    type_key: str,
    schema_version: str,
    payload: Mapping[str, object],
) -> ValidatedDraftPayload:
    """Validate and normalize one exact registry form/formset payload."""
    if not isinstance(payload, Mapping):
        raise DraftValidationError()
    if _encoded_payload_size(payload) > MAX_DRAFT_PAYLOAD_BYTES:
        raise DraftPayloadTooLarge()
    registration = _registration(type_key, schema_version)
    bundle = registration.form_provider()
    prefixes = tuple(formset.get_default_prefix() for formset in bundle.formset_classes)
    allowed = set(bundle.form_class.base_fields) | set(prefixes)
    unknown = set(payload) - allowed
    if unknown:
        raise DraftValidationError(tuple(sorted(str(name) for name in unknown)))

    form_data = {name: payload.get(name) for name in bundle.form_class.base_fields}
    form = bundle.form_class(data=form_data)
    form_valid = form.is_valid()
    validated_formsets: dict[str, forms.BaseFormSet[forms.Form]] = {}
    invalid_formsets: set[str] = set()
    formsets_valid = True
    for prefix, formset_class in zip(prefixes, bundle.formset_classes, strict=True):
        try:
            bound = formset_class(
                data=_formset_data(
                    prefix,
                    payload.get(prefix, []),
                    allowed_fields=frozenset(formset_class.form.base_fields),
                ),
                prefix=prefix,
            )
        except DraftValidationError:
            invalid_formsets.add(prefix)
            formsets_valid = False
            continue
        validated_formsets[prefix] = bound
        if not bound.is_valid():
            invalid_formsets.add(prefix)
            formsets_valid = False
    if not form_valid or not formsets_valid:
        invalid_fields = set(form.errors)
        invalid_fields.update(invalid_formsets)
        raise DraftValidationError(tuple(sorted(invalid_fields)))

    _validate_related_fields(
        case=case,
        registration=registration,
        form=form,
        formsets=validated_formsets,
    )
    normalized: dict[str, object] = {
        name: _json_value(value) for name, value in form.cleaned_data.items()
    }
    for prefix, formset in validated_formsets.items():
        normalized[prefix] = [
            {name: _json_value(value) for name, value in row.items() if name != "DELETE"}
            for row in formset.cleaned_data
            if row and not row.get("DELETE")
        ]
    if _encoded_payload_size(normalized) > MAX_DRAFT_PAYLOAD_BYTES:
        raise DraftPayloadTooLarge()
    return ValidatedDraftPayload(
        payload=normalized,
        field_names=tuple(sorted(normalized)),
    )


def _accessible_case(
    *, actor: User, case_id: UUID, for_write: bool, lock: bool = False
) -> CaseRecord:
    if not application_access_policy.has_permission(actor, ApplicationPermission.VIEW_CASES):
        raise PermissionDenied
    queryset = case_object_policy.scope_queryset(actor, CaseRecord.objects.select_related("court"))
    if lock:
        queryset = queryset.select_for_update()
    try:
        case = queryset.get(pk=case_id)
    except CaseRecord.DoesNotExist as error:
        raise PermissionDenied from error
    if for_write and not can_generate_documents_for_case(case):
        raise PermissionDenied
    return case


def _audit_draft(
    *,
    action: AuditAction,
    actor: User,
    draft: DocumentDraft,
    correlation_id: str,
    changed_fields: tuple[str, ...],
) -> None:
    record_audit_event(
        action=action,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.DOCUMENT_DRAFT, id=str(draft.pk)),
        correlation_id=correlation_id,
        changed_fields=changed_fields,
        metadata={
            "type_key": draft.type_key,
            "schema_version": draft.schema_version,
            "state": draft.state,
            "revision": draft.revision,
        },
    )


def _audit_changed_fields(
    validated: ValidatedDraftPayload,
    *,
    previous_payload: Mapping[str, object] | None,
    state_changed: bool,
) -> tuple[str, ...]:
    fields = [
        name
        for name in validated.field_names
        if previous_payload is None or previous_payload.get(name) != validated.payload.get(name)
    ]
    if state_changed:
        fields.append("state")
    fields.append("revision")
    if len(fields) <= 50:
        return tuple(fields)
    categories = ["document_fields", "revision"]
    if state_changed:
        categories.insert(1, "state")
    return tuple(categories)


@service_permission_required(ApplicationPermission.ADD_DOCUMENT_DRAFTS)
def create_document_draft(
    *,
    actor: User,
    case_id: UUID,
    type_key: str,
    schema_version: str,
    payload: Mapping[str, object],
    state: str,
    correlation_id: str,
) -> DocumentDraft:
    try:
        selected_state = DocumentDraft.State(state)
    except ValueError as error:
        raise DraftValidationError(("state",)) from error
    try:
        with transaction.atomic():
            case = _accessible_case(actor=actor, case_id=case_id, for_write=True, lock=True)
            registration = _registration(type_key, schema_version)
            if not registration.enabled:
                raise DraftSchemaMismatch("The document type is unavailable for new drafts.")
            validated = validate_document_draft_payload(
                case=case,
                type_key=type_key,
                schema_version=schema_version,
                payload=payload,
            )
            draft = DocumentDraft(
                case=case,
                type_key=type_key,
                schema_version=schema_version,
                payload=validated.payload,
                state=selected_state,
                revision=1,
                created_by=actor,
                last_edited_by=actor,
            )
            draft.save()
            _audit_draft(
                action=AuditAction.DOCUMENT_DRAFT_CREATED,
                actor=actor,
                draft=draft,
                correlation_id=correlation_id,
                changed_fields=_audit_changed_fields(
                    validated,
                    previous_payload=None,
                    state_changed=True,
                ),
            )
            return draft
    except IntegrityError as error:
        if DocumentDraft.objects.filter(
            case_id=case_id,
            type_key=type_key,
            schema_version=schema_version,
        ).exists():
            raise DraftAlreadyExists("A draft already exists for this schema.") from error
        raise


def _optimistic_update(
    queryset: QuerySet[DocumentDraft],
    *,
    expected_revision: int,
    values: dict[str, object],
) -> int:
    return queryset.filter(revision=expected_revision).update(**values)


@service_permission_required(ApplicationPermission.CHANGE_DOCUMENT_DRAFTS)
def update_document_draft(
    *,
    actor: User,
    draft_id: UUID,
    type_key: str,
    schema_version: str,
    expected_revision: int,
    payload: Mapping[str, object],
    state: str,
    correlation_id: str,
) -> DocumentDraft:
    try:
        selected_state = DocumentDraft.State(state)
    except ValueError as error:
        raise DraftValidationError(("state",)) from error
    with transaction.atomic():
        try:
            current = DocumentDraft.objects.select_related("case").get(pk=draft_id)
        except DocumentDraft.DoesNotExist as error:
            raise PermissionDenied from error
        case = _accessible_case(
            actor=actor,
            case_id=current.case_id,
            for_write=True,
            lock=True,
        )
        if current.type_key != type_key or current.schema_version != schema_version:
            raise DraftSchemaMismatch("The submitted draft identity is incompatible.")
        validated = validate_document_draft_payload(
            case=case,
            type_key=type_key,
            schema_version=schema_version,
            payload=payload,
        )
        next_revision = expected_revision + 1
        updated = _optimistic_update(
            DocumentDraft.objects.filter(pk=draft_id),
            expected_revision=expected_revision,
            values={
                "payload": validated.payload,
                "state": selected_state,
                "revision": next_revision,
                "last_edited_by": actor,
                "updated_at": timezone.now(),
            },
        )
        if updated != 1:
            raise DraftRevisionConflict("The draft was changed by another request.")
        result = DocumentDraft.objects.get(pk=draft_id)
        action = (
            AuditAction.DOCUMENT_DRAFT_STATE_CHANGED
            if current.state != selected_state
            else AuditAction.DOCUMENT_DRAFT_UPDATED
        )
        _audit_draft(
            action=action,
            actor=actor,
            draft=result,
            correlation_id=correlation_id,
            changed_fields=_audit_changed_fields(
                validated,
                previous_payload=current.payload,
                state_changed=current.state != selected_state,
            ),
        )
        return result


@service_permission_required(ApplicationPermission.VIEW_DOCUMENT_DRAFTS)
def get_document_draft(*, actor: User, draft_id: UUID, correlation_id: str) -> DocumentDraft:
    del correlation_id
    try:
        draft = DocumentDraft.objects.select_related("case").get(pk=draft_id)
    except DocumentDraft.DoesNotExist as error:
        raise PermissionDenied from error
    _accessible_case(actor=actor, case_id=draft.case_id, for_write=False)
    _registration(draft.type_key, draft.schema_version)
    return draft
