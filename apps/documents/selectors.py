from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.core.paginator import Paginator

from apps.documents.models import DocumentDraft, GeneratedDocument, TemplateVersion
from apps.documents.registry import DocumentRegistration, UnknownDocumentTypeKey, document_registry


@dataclass(frozen=True, slots=True)
class AvailableDocumentType:
    registration: DocumentRegistration
    template: TemplateVersion


@dataclass(frozen=True, slots=True)
class GenerationHistoryItem:
    id: UUID
    type_key: str
    type_code: str
    type_name: str
    status: str
    status_label: str
    actor_name: str
    reserved_at: datetime
    result_at: datetime | None
    template_version: str
    schema_version: str
    output_filename: str
    failure_summary: str


@dataclass(frozen=True, slots=True)
class GenerationHistoryPage:
    items: tuple[GenerationHistoryItem, ...]
    number: int
    num_pages: int
    has_previous: bool
    previous_page_number: int | None
    has_next: bool
    next_page_number: int | None


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


def generation_history_page(
    *, case_id: UUID, page_number: str | int | None, page_size: int = 25
) -> GenerationHistoryPage:
    """Return one bounded page containing presentation-safe generation facts only."""
    queryset = GeneratedDocument.objects.filter(case_id=case_id).values(
        "id",
        "type_key",
        "status",
        "actor__username",
        "reserved_at",
        "generated_at",
        "failed_at",
        "template_version__version",
        "schema_version",
        "output_filename",
        "failure_category",
    )
    page = Paginator(queryset, page_size).get_page(page_number)
    status_labels = dict(GeneratedDocument.Status.choices)
    failure_labels = dict(GeneratedDocument.FailureCategory.choices)
    items: list[GenerationHistoryItem] = []
    for record in page.object_list:
        type_key = str(record["type_key"])
        try:
            registration = document_registry.get(type_key)
            type_code = registration.official_code
            type_name = registration.vietnamese_name
        except UnknownDocumentTypeKey:
            type_code = type_key
            type_name = type_key
        failure_category = str(record["failure_category"])
        items.append(
            GenerationHistoryItem(
                id=record["id"],
                type_key=type_key,
                type_code=type_code,
                type_name=type_name,
                status=str(record["status"]),
                status_label=str(status_labels[str(record["status"])]),
                actor_name=str(record["actor__username"]),
                reserved_at=record["reserved_at"],
                result_at=record["generated_at"] or record["failed_at"],
                template_version=str(record["template_version__version"]),
                schema_version=str(record["schema_version"]),
                output_filename=str(record["output_filename"]),
                failure_summary=(str(failure_labels[failure_category]) if failure_category else ""),
            )
        )
    return GenerationHistoryPage(
        items=tuple(items),
        number=page.number,
        num_pages=page.paginator.num_pages,
        has_previous=page.has_previous(),
        previous_page_number=page.previous_page_number() if page.has_previous() else None,
        has_next=page.has_next(),
        next_page_number=page.next_page_number() if page.has_next() else None,
    )
