from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from apps.documents.models import DocumentDraft, TemplateVersion
from apps.documents.registry import DocumentRegistration, UnknownDocumentTypeKey, document_registry


@dataclass(frozen=True, slots=True)
class AvailableDocumentType:
    registration: DocumentRegistration
    template: TemplateVersion


def available_document_types() -> tuple[AvailableDocumentType, ...]:
    """Return only code-enabled types backed by a committed active version."""
    registrations: list[DocumentRegistration] = []
    for description in document_registry.describe():
        if not description["enabled"]:
            continue
        try:
            registrations.append(document_registry.get(str(description["key"])))
        except UnknownDocumentTypeKey:
            continue
    active_by_key = {
        template.type_key: template
        for template in TemplateVersion.objects.filter(
            type_key__in=[registration.key for registration in registrations],
            status=TemplateVersion.Status.ACTIVE,
        )
    }
    return tuple(
        AvailableDocumentType(registration=registration, template=active_by_key[registration.key])
        for registration in registrations
        if registration.key in active_by_key
    )


def compatible_case_draft(
    *, case_id: UUID, registration: DocumentRegistration
) -> DocumentDraft | None:
    return DocumentDraft.objects.filter(
        case_id=case_id,
        type_key=registration.key,
        schema_version=registration.schema_version,
    ).first()


def get_active_template(type_key: str) -> TemplateVersion | None:
    """Return the committed active version for an enabled deployed type."""
    try:
        registration = document_registry.get(type_key)
    except UnknownDocumentTypeKey:
        return None
    if not registration.enabled:
        return None
    return TemplateVersion.objects.filter(
        type_key=registration.key,
        status=TemplateVersion.Status.ACTIVE,
    ).first()
