from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.accounts.tests.test_authentication import PASSWORD
from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.models import AuditEvent
from apps.audit.recorder import AuditTarget, record_audit_event
from apps.audit.selectors import (
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT,
    AuditListFilters,
    filter_audit_events,
    list_audit_events,
    parse_audit_list_filters,
)

AUDIT_URL = reverse("audit:list")
SENSITIVE_METADATA_VALUE = "synthetic-submitted-password"


@pytest.fixture
def administrator_group() -> Group:
    return Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)


@pytest.fixture
def administrator(user_factory: Callable[..., User], administrator_group: Group) -> User:
    user = user_factory(username="synthetic-audit-view-admin", password=PASSWORD)
    user.groups.add(administrator_group)
    return user


@pytest.fixture
def audit_viewer(administrator: User) -> User:
    return administrator


def _record_event(
    *,
    action: str = AuditAction.IDENTITY_LOGIN,
    outcome: str = AuditOutcome.SUCCESS,
    actor: User | None = None,
    is_system_actor: bool = False,
    target_type: str = AuditTargetType.USER,
    target_id: str = "1",
    correlation_id: str = "synthetic-audit-view-correlation",
    occurred_at: datetime | None = None,
    metadata: dict[str, object] | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> AuditEvent:
    if occurred_at is not None:
        return AuditEvent.objects.create(
            occurred_at=occurred_at,
            actor=actor,
            is_system_actor=is_system_actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            correlation_id=correlation_id,
            changed_fields=[],
            metadata=metadata or {"reason_code": "authenticated"},
        )
    return record_audit_event(
        action=action,
        outcome=outcome,
        actor=actor,
        is_system_actor=is_system_actor,
        target=AuditTarget(type=target_type, id=target_id),
        correlation_id=correlation_id,
        metadata=metadata or {"reason_code": "authenticated"},
    )


@pytest.mark.django_db
def test_authorized_full_page_audit_list(client: Client, audit_viewer: User) -> None:
    _record_event(actor=audit_viewer, target_id=str(audit_viewer.pk))
    client.force_login(audit_viewer)

    response = client.get(AUDIT_URL)

    assert response.status_code == 200
    html = response.content.decode()
    assert "Audit log" in html or "Nhật ký kiểm tra" in html
    assert AuditAction.IDENTITY_LOGIN in html
    assert SENSITIVE_METADATA_VALUE not in html


@pytest.mark.django_db
def test_authorized_htmx_fragment_returns_results_only(client: Client, audit_viewer: User) -> None:
    _record_event(actor=audit_viewer, target_id=str(audit_viewer.pk))
    client.force_login(audit_viewer)

    response = client.get(AUDIT_URL, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    assert "HX-Request" in response.headers["Vary"]
    html = response.content.decode()
    assert "audit-data-table" in html
    assert "<html" not in html


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("principal", "expected_status"),
    [
        ("anonymous", 302),
        ("inactive", 302),
        ("non_administrator", 403),
        ("admin_without_audit_permission", 403),
        ("administrator", 200),
        ("superuser", 200),
    ],
)
def test_audit_list_authorization_matrix(
    client: Client,
    user_factory: Callable[..., User],
    administrator_group: Group,
    audit_viewer: User,
    principal: str,
    expected_status: int,
) -> None:
    _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        correlation_id="synthetic-secret-correlation-id",
    )
    if principal == "anonymous":
        user = None
    elif principal == "inactive":
        user = user_factory(username="synthetic-inactive-audit-viewer", is_active=False)
    elif principal == "non_administrator":
        user = user_factory(username="synthetic-outsider-audit-viewer")
    elif principal == "admin_without_audit_permission":
        user = user_factory(username="synthetic-restricted-audit-viewer")
        user.groups.add(administrator_group)
        user.user_permissions.clear()
        administrator_group.permissions.remove(
            administrator_group.permissions.get(codename="view_audit")
        )
    elif principal == "administrator":
        user = audit_viewer
    else:
        user = user_factory(
            username="synthetic-superuser-audit-viewer",
            is_superuser=True,
            is_staff=True,
        )

    if user is not None:
        client.force_login(user)

    response = client.get(
        AUDIT_URL,
        {"correlation_id": "synthetic-secret-correlation-id"},
    )

    assert response.status_code == expected_status
    if expected_status != 200:
        assert "synthetic-secret-correlation-id" not in response.content.decode()


@pytest.mark.django_db
def test_default_ordering_is_reverse_chronological(
    client: Client, audit_viewer: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    older = _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        correlation_id="synthetic-older-event",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        monkeypatch=monkeypatch,
    )
    newer = _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        correlation_id="synthetic-newer-event",
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        monkeypatch=monkeypatch,
    )
    client.force_login(audit_viewer)

    response = client.get(AUDIT_URL)

    html = response.content.decode()
    assert html.index(newer.correlation_id) < html.index(older.correlation_id)


@pytest.mark.django_db
def test_action_filter(client: Client, audit_viewer: User) -> None:
    _record_event(
        action=AuditAction.IDENTITY_LOGIN,
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        correlation_id="synthetic-login-filter-event",
    )
    _record_event(
        action=AuditAction.IDENTITY_LOGOUT,
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        correlation_id="synthetic-logout-filter-event",
    )
    client.force_login(audit_viewer)

    response = client.get(AUDIT_URL, {"action": AuditAction.IDENTITY_LOGOUT})

    html = response.content.decode()
    assert "synthetic-logout-filter-event" in html
    assert "synthetic-login-filter-event" not in html


@pytest.mark.django_db
def test_outcome_and_correlation_filters(client: Client, audit_viewer: User) -> None:
    _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        outcome=AuditOutcome.SUCCESS,
        correlation_id="synthetic-match-correlation",
    )
    _record_event(
        is_system_actor=True,
        target_type=AuditTargetType.APPLICATION,
        target_id="",
        outcome=AuditOutcome.FAILURE,
        correlation_id="synthetic-other-correlation",
    )
    client.force_login(audit_viewer)

    response = client.get(
        AUDIT_URL,
        {"outcome": AuditOutcome.SUCCESS, "correlation_id": "synthetic-match-correlation"},
    )

    html = response.content.decode()
    assert "synthetic-match-correlation" in html
    assert "synthetic-other-correlation" not in html


@pytest.mark.django_db
def test_actor_and_target_filters(client: Client, audit_viewer: User) -> None:
    _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        target_type=AuditTargetType.USER,
        correlation_id="synthetic-target-match",
    )
    _record_event(
        is_system_actor=True,
        target_type=AuditTargetType.APPLICATION,
        target_id="synthetic-application-target",
        correlation_id="synthetic-target-other",
    )
    client.force_login(audit_viewer)

    response = client.get(
        AUDIT_URL,
        {
            "actor": str(audit_viewer.pk),
            "target_type": AuditTargetType.USER,
            "target_id": str(audit_viewer.pk),
        },
    )

    html = response.content.decode()
    assert "synthetic-target-match" in html
    assert "synthetic-target-other" not in html


@pytest.mark.django_db
def test_invalid_filters_show_error_without_exposing_events(
    client: Client, audit_viewer: User
) -> None:
    _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        correlation_id="synthetic-hidden-on-invalid-filter",
    )
    client.force_login(audit_viewer)

    response = client.get(AUDIT_URL, {"sort": "DROP TABLE audit_auditevent;--"})

    html = response.content.decode()
    assert response.status_code == 200
    assert "synthetic-hidden-on-invalid-filter" not in html
    assert "Invalid sort value" in html or "Filter error" in html


@pytest.mark.django_db
def test_time_range_filter_and_bounds(
    client: Client, audit_viewer: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        occurred_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        correlation_id="synthetic-in-range",
        monkeypatch=monkeypatch,
    )
    _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        occurred_at=datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
        correlation_id="synthetic-out-of-range",
        monkeypatch=monkeypatch,
    )
    client.force_login(audit_viewer)

    response = client.get(
        AUDIT_URL,
        {
            "occurred_from": "2026-01-01T00:00",
            "occurred_to": "2026-01-31T23:59",
        },
    )

    html = response.content.decode()
    assert "synthetic-in-range" in html
    assert "synthetic-out-of-range" not in html

    too_wide = client.get(
        AUDIT_URL,
        {
            "occurred_from": "2020-01-01T00:00",
            "occurred_to": "2026-01-01T00:00",
        },
    )
    too_wide_html = too_wide.content.decode()
    assert "Time range exceeds" in too_wide_html or "Filter error" in too_wide_html


@pytest.mark.django_db
def test_pagination_limits(client: Client, audit_viewer: User) -> None:
    for index in range(3):
        _record_event(
            actor=audit_viewer,
            target_id=str(audit_viewer.pk),
            correlation_id=f"synthetic-page-event-{index}",
        )
    client.force_login(audit_viewer)

    response = client.get(AUDIT_URL, {"page_size": 2, "page": 2})

    html = response.content.decode()
    assert "synthetic-page-event-0" in html
    assert "synthetic-page-event-2" not in html


@pytest.mark.django_db
def test_empty_and_filtered_empty_states(client: Client, audit_viewer: User) -> None:
    client.force_login(audit_viewer)

    empty_response = client.get(AUDIT_URL)
    empty_html = empty_response.content.decode()
    assert "No audit events yet" in empty_html or "Chưa có" in empty_html

    _record_event(actor=audit_viewer, target_id=str(audit_viewer.pk))
    filtered_response = client.get(AUDIT_URL, {"action": AuditAction.IDENTITY_LOGOUT})
    assert (
        "No matching audit events" in filtered_response.content.decode()
        or "Không có" in filtered_response.content.decode()
    )


@pytest.mark.django_db
def test_javascript_disabled_filter_form_uses_get(client: Client, audit_viewer: User) -> None:
    _record_event(
        action=AuditAction.IDENTITY_LOGOUT,
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        correlation_id="synthetic-js-off",
    )
    client.force_login(audit_viewer)

    response = client.get(AUDIT_URL, {"action": AuditAction.IDENTITY_LOGOUT})

    html = response.content.decode()
    assert 'method="get"' in html
    assert f'action="{AUDIT_URL}"' in html
    assert "synthetic-js-off" in html


@pytest.mark.django_db
def test_no_mutation_routes_exist(client: Client, audit_viewer: User) -> None:
    client.force_login(audit_viewer)
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)(AUDIT_URL)
        assert response.status_code in {403, 405}


@pytest.mark.django_db
def test_metadata_is_escaped(client: Client, audit_viewer: User) -> None:
    _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        metadata={"reason_code": "<script>alert(1)</script>"},
    )
    client.force_login(audit_viewer)

    response = client.get(AUDIT_URL)

    html = response.content.decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


@pytest.mark.django_db
def test_list_audit_events_query_count(
    client: Client,
    audit_viewer: User,
    django_assert_max_num_queries: Any,
) -> None:
    for index in range(5):
        _record_event(
            actor=audit_viewer,
            target_id=str(audit_viewer.pk),
            correlation_id=f"synthetic-query-event-{index}",
        )
    client.force_login(audit_viewer)

    with django_assert_max_num_queries(16):
        response = client.get(AUDIT_URL)

    assert response.status_code == 200


@pytest.mark.django_db
def test_parse_audit_list_filters_rejects_invalid_sort() -> None:
    filters, errors = parse_audit_list_filters({"sort": "username"})
    assert errors
    assert filters.sort == DEFAULT_SORT


@pytest.mark.django_db
def test_filter_audit_events_combines_filters(audit_viewer: User) -> None:
    _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        correlation_id="synthetic-combined",
    )
    _record_event(
        actor=audit_viewer,
        target_id=str(audit_viewer.pk),
        action=AuditAction.IDENTITY_LOGOUT,
        outcome=AuditOutcome.SUCCESS,
        correlation_id="synthetic-other",
    )

    filters = AuditListFilters(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor_id=str(audit_viewer.pk),
        page_size=DEFAULT_PAGE_SIZE,
    )
    results = list(filter_audit_events(filters))

    assert len(results) == 1
    assert results[0].correlation_id == "synthetic-combined"


@pytest.mark.django_db
def test_list_audit_events_respects_page_size(
    audit_viewer: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(3):
        _record_event(
            actor=audit_viewer,
            target_id=str(audit_viewer.pk),
            correlation_id=f"synthetic-size-{index}",
            occurred_at=base + timedelta(hours=index),
            monkeypatch=monkeypatch,
        )

    page = list_audit_events(
        AuditListFilters(page_size=2, page=1, sort=DEFAULT_SORT),
    )

    assert page.total_count == 3
    assert len(page.items) == 2
