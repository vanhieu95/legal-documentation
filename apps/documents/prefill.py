from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from apps.cases.document_prefill import DocumentCaseTransfer
from apps.documents.registry import DocumentRegistration


class PrefillSource(StrEnum):
    CASE_MATTER = "case.matter_type"
    CASE_PARTICIPANT = "case.participant"
    DOCUMENT = "document"


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    source: PrefillSource
    source_label: str | Promise


@dataclass(frozen=True, slots=True)
class OverrideComparison:
    case_value: object
    draft_value: object


@dataclass(frozen=True, slots=True)
class DocumentPrefill:
    form_initial: Mapping[str, object]
    formset_initial: Mapping[str, tuple[Mapping[str, object], ...]]
    sources: Mapping[str, FieldProvenance]
    overrides: Mapping[str, OverrideComparison]


def _synthetic_prefill(
    transfer: DocumentCaseTransfer, draft_payload: Mapping[str, object]
) -> DocumentPrefill:
    shared: dict[str, object] = {"title": transfer.case.matter_type}
    first_requester = next(
        (participant for participant in transfer.participants if participant.role == "requester"),
        None,
    )
    if first_requester is not None:
        shared["participant_id"] = first_requester.id
    form_initial = {**shared, **draft_payload}
    sources = {
        "title": FieldProvenance(PrefillSource.CASE_MATTER, _("Case matter")),
        "notes": FieldProvenance(PrefillSource.DOCUMENT, _("Document value")),
        "participant_id": FieldProvenance(PrefillSource.CASE_PARTICIPANT, _("Case participant")),
    }
    overrides = {
        name: OverrideComparison(case_value=value, draft_value=draft_payload[name])
        for name, value in shared.items()
        if name in draft_payload and draft_payload[name] != value
    }
    return DocumentPrefill(
        form_initial=MappingProxyType(form_initial),
        formset_initial=MappingProxyType({}),
        sources=MappingProxyType(sources),
        overrides=MappingProxyType(overrides),
    )


def map_case_transfer(
    *,
    registration: DocumentRegistration,
    transfer: DocumentCaseTransfer,
    draft_payload: Mapping[str, object],
) -> DocumentPrefill:
    """Dispatch only to reviewed, type-owned explicit field mappings."""
    if registration.key == "synthetic-platform-test" and registration.schema_version == "v1":
        return _synthetic_prefill(transfer, draft_payload)
    raise LookupError("No deployed prefill mapping exists for this document contract.")
