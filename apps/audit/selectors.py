from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from django.contrib.auth.models import User
from django.core.paginator import EmptyPage, Paginator
from django.db.models import QuerySet
from django.utils import timezone

from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.models import AuditEvent
from apps.core.correlation import normalize_correlation_id

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 50
MAX_TIME_RANGE = timedelta(days=366)
ALLOWED_SORT_FIELDS = frozenset(
    {
        "occurred_at",
        "-occurred_at",
        "action",
        "-action",
        "outcome",
        "-outcome",
        "target_type",
        "-target_type",
        "correlation_id",
        "-correlation_id",
    }
)
DEFAULT_SORT = "-occurred_at"


@dataclass(frozen=True, slots=True)
class AuditListFilters:
    """Validated read-only audit list filters."""

    action: str = ""
    outcome: str = ""
    actor_id: str = ""
    target_type: str = ""
    target_id: str = ""
    correlation_id: str = ""
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    sort: str = DEFAULT_SORT
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    @property
    def has_active_filters(self) -> bool:
        return any(
            (
                self.action,
                self.outcome,
                self.actor_id,
                self.target_type,
                self.target_id,
                self.correlation_id,
                self.occurred_from is not None,
                self.occurred_to is not None,
            )
        )


@dataclass(frozen=True, slots=True)
class AuditListPage:
    """A bounded page of audit events for authorized browsing."""

    items: tuple[AuditEvent, ...]
    page: int
    page_count: int
    total_count: int
    page_size: int
    sort: str
    filters: AuditListFilters


def _parse_positive_int(value: str | None, *, default: int, maximum: int) -> int:
    if not value:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1:
        return default
    return min(parsed, maximum)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone=UTC)
    return parsed.astimezone(UTC)


def _validate_uuid(value: str) -> str | None:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _validate_actor_id(value: str) -> str | None:
    if value.isdigit():
        return value
    return _validate_uuid(value)


def parse_audit_list_filters(query: dict[str, Any]) -> tuple[AuditListFilters, list[str]]:
    """Parse and validate canonical audit-list query parameters."""
    errors: list[str] = []

    action = str(query.get("action", "")).strip()
    if action and action not in AuditAction:
        errors.append("Invalid action filter.")
        action = ""

    outcome = str(query.get("outcome", "")).strip()
    if outcome and outcome not in AuditOutcome:
        errors.append("Invalid outcome filter.")
        outcome = ""

    target_type = str(query.get("target_type", "")).strip()
    if target_type and target_type not in AuditTargetType:
        errors.append("Invalid target type filter.")
        target_type = ""

    target_id = str(query.get("target_id", "")).strip()
    if len(target_id) > 128:
        errors.append("Target identifier is too long.")
        target_id = ""

    actor_id = str(query.get("actor", "")).strip()
    if actor_id and _validate_actor_id(actor_id) is None:
        errors.append("Invalid actor filter.")
        actor_id = ""

    correlation_id = str(query.get("correlation_id", "")).strip()
    if correlation_id:
        normalized = normalize_correlation_id(correlation_id)
        if normalized is None:
            errors.append("Invalid correlation identifier filter.")
            correlation_id = ""
        else:
            correlation_id = normalized

    occurred_from = _parse_datetime(str(query.get("occurred_from", "")).strip() or None)
    occurred_to = _parse_datetime(str(query.get("occurred_to", "")).strip() or None)
    if occurred_from and occurred_to and occurred_from > occurred_to:
        errors.append("Start time must be before end time.")
    if occurred_from and occurred_to and occurred_to - occurred_from > MAX_TIME_RANGE:
        errors.append("Time range exceeds the allowed limit.")

    sort = str(query.get("sort", DEFAULT_SORT)).strip() or DEFAULT_SORT
    if sort not in ALLOWED_SORT_FIELDS:
        errors.append("Invalid sort value.")
        sort = DEFAULT_SORT

    page = _parse_positive_int(
        str(query.get("page", "")).strip() or None,
        default=1,
        maximum=10_000,
    )
    page_size = _parse_positive_int(
        str(query.get("page_size", "")).strip() or None,
        default=DEFAULT_PAGE_SIZE,
        maximum=MAX_PAGE_SIZE,
    )

    filters = AuditListFilters(
        action=action,
        outcome=outcome,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        correlation_id=correlation_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return filters, errors


def filter_audit_events(filters: AuditListFilters) -> QuerySet[AuditEvent]:
    """Return the authorized, filtered audit queryset."""
    queryset = AuditEvent.objects.select_related("actor")
    if filters.action:
        queryset = queryset.filter(action=filters.action)
    if filters.outcome:
        queryset = queryset.filter(outcome=filters.outcome)
    if filters.actor_id:
        queryset = queryset.filter(actor_id=int(filters.actor_id))
    if filters.target_type:
        queryset = queryset.filter(target_type=filters.target_type)
    if filters.target_id:
        queryset = queryset.filter(target_id=filters.target_id)
    if filters.correlation_id:
        queryset = queryset.filter(correlation_id=filters.correlation_id)
    if filters.occurred_from is not None:
        queryset = queryset.filter(occurred_at__gte=filters.occurred_from)
    if filters.occurred_to is not None:
        queryset = queryset.filter(occurred_at__lte=filters.occurred_to)
    return queryset.order_by(filters.sort, "-id")


def list_audit_events(filters: AuditListFilters) -> AuditListPage:
    """Return a bounded page of audit events."""
    queryset = filter_audit_events(filters)
    paginator = Paginator(queryset, filters.page_size)
    try:
        page_obj = paginator.page(filters.page)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    return AuditListPage(
        items=tuple(page_obj.object_list),
        page=page_obj.number,
        page_count=paginator.num_pages,
        total_count=paginator.count,
        page_size=filters.page_size,
        sort=filters.sort,
        filters=filters,
    )


def actor_filter_choices() -> QuerySet[User]:
    """Return distinct actors that appear in audit events for selector options."""
    actor_ids = (
        AuditEvent.objects.exclude(actor_id__isnull=True)
        .values_list("actor_id", flat=True)
        .distinct()
        .order_by("actor_id")
    )
    return User.objects.filter(pk__in=actor_ids).order_by("username")
