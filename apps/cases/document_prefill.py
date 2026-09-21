from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch

from apps.accounts.policies import ApplicationPermission, application_access_policy
from apps.cases.models import (
    CaseOfficialAssignment,
    CaseParticipant,
    CaseRecord,
    EntityAddress,
    Hearing,
    Representation,
)
from apps.cases.policies import case_object_policy


@dataclass(frozen=True, slots=True)
class AuthorizedDocumentCase:
    actor: User
    case_id: UUID


@dataclass(frozen=True, slots=True)
class CourtTransfer:
    code: str
    full_name: str
    short_name: str
    level: str
    address: str


@dataclass(frozen=True, slots=True)
class CaseTransfer:
    id: UUID
    internal_reference: str
    matter_type: str
    procedural_stage: str
    status: str
    acceptance_number: str
    acceptance_year: int | None
    acceptance_date: date | None
    acceptance_type_code: str


@dataclass(frozen=True, slots=True)
class ParticipantTransfer:
    id: UUID
    entity_id: UUID
    role: str
    ordering: int
    kind: str
    legal_name: str
    display_name: str
    identity_document_number: str
    registration_number: str
    date_of_birth: date | None
    organization_type: str
    address: str
    workplace: str
    contact: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class RepresentationTransfer:
    id: UUID
    represented_participant_id: UUID
    representative_entity_id: UUID
    representative_name: str
    representation_type: str
    authority_reference: str
    authority_date: date | None
    description: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class OfficialAssignmentTransfer:
    id: UUID
    official_id: UUID
    official_name: str
    title: str
    position: str
    role: str
    ordering: int
    effective_from: date
    effective_to: date | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class HearingTransfer:
    id: UUID
    instance_level: str
    scheduled_at: datetime
    location: str
    status: str


@dataclass(frozen=True, slots=True)
class DocumentCaseTransfer:
    court: CourtTransfer
    case: CaseTransfer
    participants: tuple[ParticipantTransfer, ...]
    representations: tuple[RepresentationTransfer, ...]
    assignments: tuple[OfficialAssignmentTransfer, ...]
    hearings: tuple[HearingTransfer, ...]


def authorize_document_case(*, actor: User, case_id: UUID) -> AuthorizedDocumentCase:
    """Issue a context only after canonical permission and object-policy scoping."""
    application_access_policy.require_permission(actor, ApplicationPermission.VIEW_CASES)
    if (
        not case_object_policy.scope_queryset(actor, CaseRecord.objects.all())
        .filter(pk=case_id)
        .exists()
    ):
        raise PermissionDenied
    return AuthorizedDocumentCase(actor=actor, case_id=case_id)


def _preferred_address(participant: CaseParticipant) -> str:
    if participant.case_address:
        return participant.case_address
    priorities: dict[str, int] = {
        EntityAddress.Kind.CONTACT: 0,
        EntityAddress.Kind.CURRENT: 1,
        EntityAddress.Kind.PERMANENT: 2,
        EntityAddress.Kind.REGISTERED_OFFICE: 3,
    }
    addresses = sorted(
        (address for address in participant.entity.addresses.all() if address.is_active),
        key=lambda address: (priorities[address.kind], address.id),
    )
    return addresses[0].full_address if addresses else ""


def document_case_transfer(context: AuthorizedDocumentCase) -> DocumentCaseTransfer:
    """Materialize the approved immutable one-way document-prefill value."""
    if not isinstance(context, AuthorizedDocumentCase):
        raise TypeError("An authorized document case context is required.")
    application_access_policy.require_permission(context.actor, ApplicationPermission.VIEW_CASES)
    participants = (
        CaseParticipant.objects.select_related("entity")
        .prefetch_related(
            Prefetch(
                "entity__addresses",
                queryset=EntityAddress.objects.filter(is_active=True).order_by("kind", "id"),
            )
        )
        .order_by("ordering", "id")
    )
    queryset = case_object_policy.scope_queryset(
        context.actor, CaseRecord.objects.select_related("court")
    )
    try:
        case = queryset.prefetch_related(
            Prefetch("participants", queryset=participants),
            Prefetch(
                "representations",
                queryset=Representation.objects.select_related(
                    "representative_entity", "represented_participant"
                ).order_by("id"),
            ),
            Prefetch(
                "official_assignments",
                queryset=CaseOfficialAssignment.objects.select_related("official__entity").order_by(
                    "ordering", "id"
                ),
            ),
            Prefetch("hearings", queryset=Hearing.objects.order_by("scheduled_at", "id")),
        ).get(pk=context.case_id)
    except CaseRecord.DoesNotExist as error:
        raise PermissionDenied from error
    return DocumentCaseTransfer(
        court=CourtTransfer(
            code=case.court.code,
            full_name=case.court.full_name,
            short_name=case.court.short_name,
            level=case.court.level,
            address=case.court.address,
        ),
        case=CaseTransfer(
            id=case.pk,
            internal_reference=case.internal_reference,
            matter_type=case.matter_type,
            procedural_stage=case.procedural_stage,
            status=case.status,
            acceptance_number=case.acceptance_number,
            acceptance_year=case.acceptance_year,
            acceptance_date=case.acceptance_date,
            acceptance_type_code=case.acceptance_type_code,
        ),
        participants=tuple(
            ParticipantTransfer(
                id=participant.pk,
                entity_id=participant.entity_id,
                role=participant.role,
                ordering=participant.ordering,
                kind=participant.entity.kind,
                legal_name=participant.entity.legal_name,
                display_name=participant.entity.display_name or participant.entity.legal_name,
                identity_document_number=participant.entity.identity_document_number,
                registration_number=participant.entity.registration_number,
                date_of_birth=participant.entity.date_of_birth,
                organization_type=participant.entity.organization_type,
                address=_preferred_address(participant),
                workplace=participant.case_workplace,
                contact=participant.case_contact,
                is_active=participant.is_active,
            )
            for participant in case.participants.all()
        ),
        representations=tuple(
            RepresentationTransfer(
                id=representation.pk,
                represented_participant_id=representation.represented_participant_id,
                representative_entity_id=representation.representative_entity_id,
                representative_name=(
                    representation.representative_entity.display_name
                    or representation.representative_entity.legal_name
                ),
                representation_type=representation.representation_type,
                authority_reference=representation.authority_reference,
                authority_date=representation.authority_date,
                description=representation.description,
                is_active=representation.is_active,
            )
            for representation in case.representations.all()
        ),
        assignments=tuple(
            OfficialAssignmentTransfer(
                id=assignment.pk,
                official_id=assignment.official_id,
                official_name=(
                    assignment.official.entity.display_name or assignment.official.entity.legal_name
                ),
                title=assignment.official.title,
                position=assignment.official.position,
                role=assignment.role,
                ordering=assignment.ordering,
                effective_from=assignment.effective_from,
                effective_to=assignment.effective_to,
                is_active=assignment.is_active,
            )
            for assignment in case.official_assignments.all()
        ),
        hearings=tuple(
            HearingTransfer(
                id=hearing.pk,
                instance_level=hearing.instance_level,
                scheduled_at=hearing.scheduled_at,
                location=hearing.location,
                status=hearing.status,
            )
            for hearing in case.hearings.all()
        ),
    )
