from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, cast

from django.core.paginator import EmptyPage, Page, Paginator
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.cases.models import (
    CaseOfficialAssignment,
    CaseRecord,
    Court,
    Entity,
    EntityAddress,
    Hearing,
    Official,
)

ReferenceType = Literal["courts", "entities", "addresses", "officials"]
ReferenceRecord = Court | Entity | EntityAddress | Official
REFERENCE_PAGE_SIZE = 25


@dataclass(frozen=True, slots=True)
class ReferenceListPage:
    items: tuple[ReferenceRecord, ...]
    page: int
    page_count: int
    total_count: int
    has_previous: bool
    has_next: bool


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
