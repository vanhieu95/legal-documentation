from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.urls import reverse

from apps.accounts.policies import ApplicationPermission, application_access_policy
from apps.cases.selectors import policy_scoped_case_queryset
from apps.documents.models import GeneratedDocument, TemplateVersion
from apps.documents.registry import UnknownDocumentTypeKey, document_registry

DASHBOARD_GENERATION_LIMIT = 5
MVP_DOCUMENT_TYPE_CODES = (
    ("vds-01", "01-VDS"),
    ("vds-03", "03-VDS"),
    ("vds-10", "10-VDS"),
    ("vds-05", "05-VDS"),
    ("vds-09", "09-VDS"),
    ("vds-15", "15-VDS"),
    ("vds-21", "21-VDS"),
    ("vds-31", "31-VDS"),
    ("vds-22", "22-VDS"),
    ("vds-11", "11-VDS"),
    ("vds-04", "04-VDS"),
    ("vds-12", "12-VDS"),
)


@dataclass(frozen=True, slots=True)
class DashboardTemplateCoverage:
    type_key: str
    official_code: str
    is_deployed: bool
    has_active_template: bool
    upload_url: str | None


@dataclass(frozen=True, slots=True)
class DashboardGeneration:
    id: UUID
    case_id: UUID
    case_reference: str
    type_code: str
    type_name: str
    status: str
    status_label: str
    occurred_at: datetime
    history_url: str


@dataclass(frozen=True, slots=True)
class DocumentDashboardSummary:
    template_coverage: tuple[DashboardTemplateCoverage, ...]
    active_template_count: int
    template_total: int
    recent_attempts: tuple[DashboardGeneration, ...]
    failed_attempts: tuple[DashboardGeneration, ...]
    failed_total: int
    failed_attention_url: str | None


def _attempt_rows(
    queryset: QuerySet[GeneratedDocument], *, limit: int
) -> tuple[DashboardGeneration, ...]:
    records = queryset.values(
        "id",
        "case_id",
        "case__internal_reference",
        "type_key",
        "status",
        "reserved_at",
    ).order_by("-reserved_at", "id")[:limit]
    status_labels = dict(GeneratedDocument.Status.choices)
    rows: list[DashboardGeneration] = []
    for record in records:
        type_key = str(record["type_key"])
        try:
            registration = document_registry.get(type_key)
            type_code = registration.official_code
            type_name = registration.vietnamese_name
        except UnknownDocumentTypeKey:
            type_code = type_key
            type_name = type_key
        status = str(record["status"])
        rows.append(
            DashboardGeneration(
                id=record["id"],
                case_id=record["case_id"],
                case_reference=str(record["case__internal_reference"]),
                type_code=type_code,
                type_name=type_name,
                status=status,
                status_label=str(status_labels[status]),
                occurred_at=record["reserved_at"],
                history_url=reverse("documents:case-generation-history", args=[record["case_id"]]),
            )
        )
    return tuple(rows)


def _template_coverage() -> tuple[DashboardTemplateCoverage, ...]:
    deployed = {
        str(description["key"]): description
        for description in document_registry.describe()
        if description["enabled"] and not description["is_synthetic"]
    }
    deployed_mvp_keys = tuple(key for key, _code in MVP_DOCUMENT_TYPE_CODES if key in deployed)
    active_keys = set(
        TemplateVersion.objects.filter(
            type_key__in=deployed_mvp_keys,
            status=TemplateVersion.Status.ACTIVE,
        ).values_list("type_key", flat=True)
    )
    return tuple(
        DashboardTemplateCoverage(
            type_key=key,
            official_code=code,
            is_deployed=key in deployed,
            has_active_template=key in active_keys,
            upload_url=(
                reverse("documents:template-upload", args=[key]) if key in deployed else None
            ),
        )
        for key, code in MVP_DOCUMENT_TYPE_CODES
    )


def document_dashboard_summary(*, actor: User) -> DocumentDashboardSummary:
    """Return bounded, policy-scoped document operations facts for the dashboard."""
    application_access_policy.require_permission(actor, ApplicationPermission.VIEW_TEMPLATES)
    application_access_policy.require_permission(actor, ApplicationPermission.VIEW_DOCUMENT_HISTORY)
    visible_cases = policy_scoped_case_queryset(actor=actor).values("id")
    attempts = GeneratedDocument.objects.filter(case_id__in=visible_cases)
    coverage = _template_coverage()
    failed = attempts.filter(status=GeneratedDocument.Status.FAILED)
    failed_attempts = _attempt_rows(failed, limit=DASHBOARD_GENERATION_LIMIT)
    return DocumentDashboardSummary(
        template_coverage=coverage,
        active_template_count=sum(item.has_active_template for item in coverage),
        template_total=len(coverage),
        recent_attempts=_attempt_rows(attempts, limit=DASHBOARD_GENERATION_LIMIT),
        failed_attempts=failed_attempts,
        failed_total=failed.count(),
        failed_attention_url=(failed_attempts[0].history_url if failed_attempts else None),
    )
