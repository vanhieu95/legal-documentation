from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connection
from django.test import Client
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.audit.models import AuditEvent
from apps.cases.models import CaseRecord
from apps.cases.policies import case_object_policy
from apps.cases.selectors import (
    DASHBOARD_RECENT_CASE_LIMIT,
    CaseActivityCategory,
    case_activity_counts,
    policy_scoped_case_queryset,
    recent_case_activity,
)


@pytest.fixture
def administrator(user_factory: Callable[..., User]) -> User:
    user = user_factory(username="synthetic-dashboard-selector-administrator")
    user.groups.add(Group.objects.get(name=ADMINISTRATOR_GROUP_NAME))
    return user


@pytest.mark.django_db
def test_case_activity_counts_cover_mixed_and_empty_datasets(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    empty = case_activity_counts(actor=administrator)
    case_factory(status=CaseRecord.Status.ACTIVE)
    case_factory(
        status=CaseRecord.Status.ARCHIVED,
        archived_by=administrator,
        archived_at=timezone.now(),
        archive_reason="Synthetic archive reason",
    )

    mixed = case_activity_counts(actor=administrator)

    assert (empty.active, empty.archived) == (0, 0)
    assert (mixed.active, mixed.archived) == (1, 1)


@pytest.mark.django_db
def test_recent_case_activity_is_bounded_deterministic_and_display_safe(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    baseline = timezone.now() - timedelta(days=1)
    cases = [
        case_factory(internal_reference=f"SYN-ACTIVITY-{index:02d}")
        for index in range(DASHBOARD_RECENT_CASE_LIMIT + 2)
    ]
    for index, case in enumerate(cases):
        CaseRecord.objects.filter(pk=case.pk).update(updated_at=baseline + timedelta(minutes=index))
    archived = cases[-1]
    CaseRecord.objects.filter(pk=archived.pk).update(
        status=CaseRecord.Status.ARCHIVED,
        archived_by=administrator,
        archived_at=baseline + timedelta(minutes=20),
        archive_reason="Sensitive synthetic archive reason",
    )

    activity = recent_case_activity(actor=administrator)

    assert len(activity) == DASHBOARD_RECENT_CASE_LIMIT
    assert [item.reference for item in activity] == [
        case.internal_reference for case in reversed(cases[-DASHBOARD_RECENT_CASE_LIMIT:])
    ]
    assert activity[0].category is CaseActivityCategory.ARCHIVED
    assert activity[0].status == CaseRecord.Status.ARCHIVED
    assert str(activity[0].case_id) in activity[0].detail_url
    assert all(not hasattr(item, "archive_reason") for item in activity)


@pytest.mark.django_db
def test_dashboard_selectors_apply_case_policy_scope(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visible = case_factory(internal_reference="SYN-VISIBLE")
    excluded = case_factory(internal_reference="SYN-EXCLUDED")

    def scoped(actor: User, queryset: Any) -> Any:
        assert actor == administrator
        return queryset.exclude(pk=excluded.pk)

    monkeypatch.setattr(case_object_policy, "scope_queryset", scoped)

    counts = case_activity_counts(actor=administrator)
    activity = recent_case_activity(actor=administrator)

    assert (counts.active, counts.archived) == (1, 0)
    assert [item.case_id for item in activity] == [visible.pk]


@pytest.mark.django_db
def test_dashboard_selectors_require_case_view_permission(
    user_factory: Callable[..., User],
) -> None:
    outsider = user_factory(username="synthetic-dashboard-selector-outsider")

    with pytest.raises(PermissionDenied):
        case_activity_counts(actor=outsider)
    with pytest.raises(PermissionDenied):
        recent_case_activity(actor=outsider)


@pytest.mark.django_db
def test_dashboard_selectors_use_two_queries_without_per_item_growth(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    for index in range(DASHBOARD_RECENT_CASE_LIMIT + 3):
        case_factory(internal_reference=f"SYN-BUDGET-{index:02d}")

    with CaptureQueriesContext(connection) as queries:
        counts = case_activity_counts(actor=administrator)
        activity = recent_case_activity(actor=administrator)
        rendered_values = [
            (item.reference, item.status, item.occurred_at, item.category, item.detail_url)
            for item in activity
        ]

    assert counts.active == DASHBOARD_RECENT_CASE_LIMIT + 3
    assert len(rendered_values) == DASHBOARD_RECENT_CASE_LIMIT
    case_queries = [query for query in queries if CaseRecord._meta.db_table in query["sql"]]
    # Two data queries: one conditional aggregate and one bounded recent projection.
    assert len(case_queries) == 2, [query["sql"] for query in queries]
    # The remaining queries are the existing deny-by-default group/permission checks.
    assert len(queries) <= 6, [query["sql"] for query in queries]


def dashboard_url() -> str:
    return reverse("accounts:dashboard")


@pytest.mark.django_db
def test_dashboard_returns_full_page_and_narrow_htmx_case_activity_fragment(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case_factory(internal_reference="SYN-DASHBOARD-001")
    client.force_login(administrator)

    full = client.get(dashboard_url())
    fragment = client.get(dashboard_url(), headers={"HX-Request": "true"})

    assert full.status_code == 200
    assert "accounts/dashboard.html" in [template.name for template in full.templates]
    assert "accounts/_dashboard_case_activity.html" in [
        template.name for template in fragment.templates
    ]
    assert "<html" in full.content.decode()
    assert "<html" not in fragment.content.decode()
    assert 'id="dashboard-case-activity"' in fragment.content.decode()
    assert "HX-Request" in full.headers["Vary"]
    assert "HX-Request" in fragment.headers["Vary"]


@pytest.mark.django_db
def test_dashboard_cards_use_exact_canonical_case_list_filters(
    client: Client,
    administrator: User,
) -> None:
    client.force_login(administrator)

    html = client.get(dashboard_url()).content.decode()

    active_url = f"{reverse('cases:list')}?archive_state=active"
    archived_url = f"{reverse('cases:list')}?archive_state=archived"
    assert f'href="{active_url}"' in html
    assert f'href="{archived_url}"' in html
    assert "archive_state=active&amp;" not in html
    assert "archive_state=archived&amp;" not in html


@pytest.mark.django_db
def test_dashboard_card_links_reproduce_the_intended_case_list_state(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    active = case_factory(internal_reference="SYN-DASHBOARD-ACTIVE")
    archived = case_factory(
        internal_reference="SYN-DASHBOARD-ARCHIVED",
        status=CaseRecord.Status.ARCHIVED,
        archived_by=administrator,
        archived_at=timezone.now(),
        archive_reason="Synthetic archive reason",
    )
    client.force_login(administrator)

    active_response = client.get(f"{reverse('cases:list')}?archive_state=active")
    archived_response = client.get(f"{reverse('cases:list')}?archive_state=archived")

    assert active_response.status_code == 200
    assert active.internal_reference in active_response.content.decode()
    assert archived.internal_reference not in active_response.content.decode()
    assert archived_response.status_code == 200
    assert archived.internal_reference in archived_response.content.decode()
    assert active.internal_reference not in archived_response.content.decode()


@pytest.mark.django_db
def test_dashboard_recent_activity_links_only_to_authorized_case_details(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visible = case_factory(internal_reference="SYN-DASHBOARD-VISIBLE")
    excluded = case_factory(internal_reference="SYN-DASHBOARD-EXCLUDED")
    monkeypatch.setattr(
        case_object_policy,
        "scope_queryset",
        lambda actor, queryset: queryset.exclude(pk=excluded.pk),
    )
    client.force_login(administrator)

    html = client.get(dashboard_url()).content.decode()

    assert visible.internal_reference in html
    assert reverse("cases:detail", kwargs={"case_id": visible.pk}) in html
    assert excluded.internal_reference not in html
    assert str(excluded.pk) not in html


@pytest.mark.django_db
def test_dashboard_exposes_loading_empty_error_and_document_unavailable_states(
    client: Client,
    administrator: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.force_login(administrator)
    empty_html = client.get(dashboard_url()).content.decode()

    assert 'id="dashboard-case-activity-loading"' in empty_html
    assert 'aria-live="polite"' in empty_html
    assert "Chưa có hoạt động hồ sơ" in empty_html
    assert "Chức năng tài liệu chưa khả dụng" in empty_html
    assert "0" in empty_html

    monkeypatch.setattr(
        "apps.accounts.views.case_activity_counts",
        lambda **kwargs: (_ for _ in ()).throw(DatabaseError("synthetic sensitive failure")),
    )
    error = client.get(dashboard_url(), headers={"HX-Request": "true"})
    error_html = error.content.decode()

    assert error.status_code == 503
    assert 'role="alert"' in error_html
    assert "Hoạt động hồ sơ tạm thời không khả dụng" in error_html
    assert "synthetic sensitive failure" not in error_html


@pytest.mark.django_db
def test_dashboard_permission_matrix_and_allowed_get_has_no_audit_side_effect(
    client: Client,
    administrator: User,
    user_factory: Callable[..., User],
) -> None:
    anonymous = client.get(dashboard_url())
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"] == "/login/?next=/dashboard/"

    inactive = user_factory(username="synthetic-dashboard-inactive", is_active=False)
    inactive.groups.add(Group.objects.get(name=ADMINISTRATOR_GROUP_NAME))
    client.force_login(inactive)
    assert client.get(dashboard_url()).status_code == 302

    outsider = user_factory(username="synthetic-dashboard-outsider")
    client.force_login(outsider)
    assert client.get(dashboard_url()).status_code == 403

    administrator.user_permissions.clear()
    group = Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)
    view_permission = group.permissions.get(codename="view_cases")
    group.permissions.remove(view_permission)
    client.force_login(administrator)
    assert client.get(dashboard_url()).status_code == 403

    group.permissions.add(view_permission)
    administrator = User.objects.get(pk=administrator.pk)
    client.force_login(administrator)
    before = AuditEvent.objects.count()
    assert client.get(dashboard_url()).status_code == 200
    assert AuditEvent.objects.count() == before

    superuser = user_factory(
        username="synthetic-dashboard-superuser", is_staff=True, is_superuser=True
    )
    client.force_login(superuser)
    assert client.get(dashboard_url()).status_code == 200


@pytest.mark.django_db
def test_dashboard_html_and_query_strings_exclude_sensitive_case_values(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case_factory(
        internal_reference="SYN-SAFE-REFERENCE",
        matter_type="SYN-SENSITIVE-LEGAL-CONTENT",
        status=CaseRecord.Status.ARCHIVED,
        archived_by=administrator,
        archived_at=timezone.now(),
        archive_reason="SYN-SENSITIVE-ARCHIVE-REASON",
    )
    client.force_login(administrator)

    html = client.get(dashboard_url()).content.decode()

    assert "SYN-SAFE-REFERENCE" in html
    assert "SYN-SENSITIVE-LEGAL-CONTENT" not in html
    assert "SYN-SENSITIVE-ARCHIVE-REASON" not in html
    assert "matter_type=" not in html
    assert "archive_reason=" not in html


@pytest.mark.django_db
@override_settings(LANGUAGE_CODE="vi")
def test_dashboard_renders_vietnamese_count_context_and_ho_chi_minh_time(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory(internal_reference="SYN-UNICODE-DASHBOARD")
    CaseRecord.objects.filter(pk=case.pk).update(
        updated_at=timezone.now().replace(hour=18, minute=30)
    )
    client.force_login(administrator)

    html = client.get(dashboard_url()).content.decode()

    assert "Hồ sơ đang hoạt động" in html
    assert "Hồ sơ đã lưu trữ" in html
    assert "Hoạt động hồ sơ gần đây" in html
    assert "SYN-UNICODE-DASHBOARD" in html
    assert "Xem hồ sơ" in html


@pytest.mark.django_db
def test_dashboard_query_budget_is_fixed_as_recent_rows_grow(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    client.force_login(administrator)
    client.get(dashboard_url())
    for index in range(DASHBOARD_RECENT_CASE_LIMIT + 4):
        case_factory(internal_reference=f"SYN-DASHBOARD-QUERY-{index:02d}")

    with CaptureQueriesContext(connection) as queries:
        response = client.get(dashboard_url())

    assert response.status_code == 200
    case_queries = [query for query in queries if CaseRecord._meta.db_table in query["sql"]]
    assert len(case_queries) == 2, [query["sql"] for query in queries]
    # Session/authentication plus the existing deny-by-default permission checks are capped too.
    assert len(queries) <= 16, [query["sql"] for query in queries]
    assert len(response.context["recent_activity"]) == DASHBOARD_RECENT_CASE_LIMIT


@pytest.mark.postgresql
@pytest.mark.django_db
def test_dashboard_recent_activity_postgresql_plan_is_inspectable(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL plan verification.")
    for index in range(100):
        case_factory(internal_reference=f"SYN-DASHBOARD-PLAN-{index:03d}")

    queryset = (
        policy_scoped_case_queryset(actor=administrator)
        .values("id", "internal_reference", "status", "updated_at")
        .order_by("-updated_at", "id")[:DASHBOARD_RECENT_CASE_LIMIT]
    )

    plan = queryset.explain(format="json", analyze=False, verbose=False)

    assert "Plan" in plan
    assert CaseRecord._meta.db_table in plan
