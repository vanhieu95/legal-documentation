from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, cast

from django.contrib.auth.models import User
from django.core.paginator import EmptyPage, Page, Paginator
from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from apps.accounts.policies import ApplicationPermission, application_access_policy
from apps.cases.forms import CaseListQueryForm
from apps.cases.models import (
    CaseOfficialAssignment,
    CaseParticipant,
    CaseRecord,
    Court,
    Entity,
    EntityAddress,
    Hearing,
    Official,
    Representation,
)
from apps.cases.policies import case_object_policy

ReferenceType = Literal["courts", "entities", "addresses", "officials"]
ReferenceRecord = Court | Entity | EntityAddress | Official
REFERENCE_PAGE_SIZE = 25
CASE_SORT_FIELDS = {
    "updated": "updated_at",
    "created": "created_at",
    "acceptance_date": "acceptance_date",
    "acceptance_number": "acceptance_number",
    "court": "court__full_name",
    "matter_type": "matter_type",
}


@dataclass(frozen=True, slots=True)
class ReferenceListPage:
    items: tuple[ReferenceRecord, ...]
    page: int
    page_count: int
    total_count: int
    has_previous: bool
    has_next: bool


@dataclass(frozen=True, slots=True)
class CaseListPage:
    items: tuple[CaseRecord, ...]
    page: int
    page_size: int
    page_count: int
    total_count: int
    has_previous: bool
    has_next: bool


def _search_cases(queryset: QuerySet[CaseRecord], query: str) -> QuerySet[CaseRecord]:
    if not query:
        return queryset
    identifiers = (
        Q(internal_reference__istartswith=query)
        | Q(acceptance_number__istartswith=query)
        | Q(acceptance_type_code__istartswith=query)
        | Q(court__code__istartswith=query)
    )
    if query.isdecimal() and 1900 <= int(query) <= 9999:
        identifiers |= Q(acceptance_year=int(query))
    text = (
        Q(matter_type__icontains=query)
        | Q(court__full_name__icontains=query)
        | Q(court__short_name__icontains=query)
        | Q(participants__entity__legal_name__icontains=query)
        | Q(participants__entity__display_name__icontains=query)
        | Q(representations__representative_entity__legal_name__icontains=query)
        | Q(representations__representative_entity__display_name__icontains=query)
    )
    return queryset.filter(identifiers | text).distinct()


def case_search_queryset(*, actor: User, form: CaseListQueryForm) -> QuerySet[CaseRecord]:
    """Return a permission- and object-policy-scoped case discovery queryset."""
    application_access_policy.require_permission(actor, ApplicationPermission.VIEW_CASES)
    if not form.is_valid():
        raise ValueError("A valid case list query form is required.")
    filters = form.cleaned_data
    queryset = case_object_policy.scope_queryset(
        actor,
        CaseRecord.objects.select_related("court").prefetch_related(
            Prefetch(
                "participants",
                queryset=CaseParticipant.objects.select_related("entity").order_by(
                    "ordering", "id"
                ),
            ),
            Prefetch(
                "representations",
                queryset=Representation.objects.select_related(
                    "representative_entity", "represented_participant"
                ).order_by("id"),
            ),
        ),
    )
    queryset = _search_cases(queryset, filters["q"])
    if filters.get("court"):
        queryset = queryset.filter(court=filters["court"])
    if filters.get("status"):
        queryset = queryset.filter(status=filters["status"])
    if filters.get("procedural_stage"):
        queryset = queryset.filter(procedural_stage=filters["procedural_stage"])
    if filters.get("acceptance_type_code"):
        queryset = queryset.filter(acceptance_type_code=filters["acceptance_type_code"])
    if filters.get("acceptance_year"):
        queryset = queryset.filter(acceptance_year=filters["acceptance_year"])
    if filters.get("acceptance_date_from"):
        queryset = queryset.filter(acceptance_date__gte=filters["acceptance_date_from"])
    if filters.get("acceptance_date_to"):
        queryset = queryset.filter(acceptance_date__lte=filters["acceptance_date_to"])
    if filters["archive_state"] != "all":
        queryset = queryset.filter(status=filters["archive_state"])
    sort = filters["sort"]
    descending = sort.startswith("-")
    sort_key = sort.removeprefix("-")
    order_field = CASE_SORT_FIELDS[sort_key]
    if descending:
        order_field = f"-{order_field}"
    return queryset.order_by(order_field, "id")


def list_cases(*, actor: User, form: CaseListQueryForm) -> CaseListPage:
    queryset = case_search_queryset(actor=actor, form=form)
    page_size = form.cleaned_data["page_size"]
    paginator = Paginator(queryset, page_size)
    try:
        selected: Page[CaseRecord] = paginator.page(form.cleaned_data["page"])
    except EmptyPage:
        selected = paginator.page(paginator.num_pages)
    return CaseListPage(
        items=tuple(selected.object_list),
        page=selected.number,
        page_size=page_size,
        page_count=paginator.num_pages,
        total_count=paginator.count,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def reference_queryset(reference_type: ReferenceType) -> QuerySet[ReferenceRecord]:
    if reference_type == "courts":
        return cast(QuerySet[ReferenceRecord], Court.objects.select_related("superior_court"))
    if reference_type == "entities":
        return cast(QuerySet[ReferenceRecord], Entity.objects.all())
    if reference_type == "addresses":
        return cast(QuerySet[ReferenceRecord], EntityAddress.objects.select_related("entity"))
    return cast(QuerySet[ReferenceRecord], Official.objects.select_related("entity", "home_court"))


def filter_reference_queryset(
    queryset: QuerySet[ReferenceRecord], *, reference_type: ReferenceType, query: str, state: str
) -> QuerySet[ReferenceRecord]:
    if state == "active":
        queryset = queryset.filter(is_active=True)
    elif state == "inactive":
        queryset = queryset.filter(is_active=False)

    if not query:
        return queryset
    if reference_type == "courts":
        return queryset.filter(
            Q(code__istartswith=query)
            | Q(full_name__icontains=query)
            | Q(short_name__icontains=query)
        )
    if reference_type == "entities":
        return queryset.filter(Q(legal_name__icontains=query) | Q(display_name__icontains=query))
    if reference_type == "addresses":
        return queryset.filter(
            Q(full_address__icontains=query)
            | Q(province__icontains=query)
            | Q(district__icontains=query)
            | Q(ward__icontains=query)
            | Q(entity__legal_name__icontains=query)
        )
    return queryset.filter(
        Q(entity__legal_name__icontains=query)
        | Q(home_court__full_name__icontains=query)
        | Q(title__icontains=query)
        | Q(position__icontains=query)
    )


def list_references(
    *, reference_type: ReferenceType, query: str = "", state: str = "active", page: int = 1
) -> ReferenceListPage:
    queryset = filter_reference_queryset(
        reference_queryset(reference_type),
        reference_type=reference_type,
        query=query,
        state=state,
    )
    paginator = Paginator(queryset, REFERENCE_PAGE_SIZE)
    try:
        selected: Page[ReferenceRecord] = paginator.page(page)
    except EmptyPage:
        selected = paginator.page(paginator.num_pages)
    return ReferenceListPage(
        items=tuple(selected.object_list),
        page=selected.number,
        page_count=paginator.num_pages,
        total_count=paginator.count,
        has_previous=selected.has_previous(),
        has_next=selected.has_next(),
    )


def current_case_assignments(
    *, case: CaseRecord, on_date: date | None = None
) -> QuerySet[CaseOfficialAssignment]:
    selected_date = on_date or timezone.localdate()
    return (
        CaseOfficialAssignment.objects.filter(
            case=case,
            is_active=True,
            effective_from__lte=selected_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=selected_date))
        .select_related("official", "official__entity")
        .order_by("ordering", "id")
    )


def upcoming_case_hearings(
    *, case: CaseRecord, from_time: datetime | None = None
) -> QuerySet[Hearing]:
    selected_time = from_time or timezone.now()
    return Hearing.objects.filter(
        case=case,
        status=Hearing.Status.SCHEDULED,
        scheduled_at__gte=selected_time,
    ).order_by("scheduled_at", "id")


def case_overview_queryset() -> QuerySet[CaseRecord]:
    """Load overview relations with a fixed number of queries."""
    return CaseRecord.objects.select_related(
        "court", "created_by", "last_edited_by"
    ).prefetch_related("participants", "representations", "official_assignments", "hearings")
