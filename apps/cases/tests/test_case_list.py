from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.accounts.sessions import SESSION_LAST_ACTIVITY_KEY, SESSION_STARTED_AT_KEY
from apps.audit.models import AuditEvent
from apps.cases.models import CaseRecord, Court


@pytest.fixture
def administrator(user_factory: Callable[..., User]) -> User:
    user = user_factory(username="synthetic-case-list-admin")
    user.groups.add(Group.objects.get(name=ADMINISTRATOR_GROUP_NAME))
    return user


def list_url() -> str:
    return reverse("cases:list")


@pytest.mark.django_db
def test_case_list_returns_full_page_and_narrow_htmx_fragment(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory(internal_reference="SYN-LIST-001")
    client.force_login(administrator)

    full = client.get(list_url())
    fragment = client.get(list_url(), HTTP_HX_REQUEST="true")

    assert full.status_code == 200
    assert "cases/list.html" in [template.name for template in full.templates]
    assert "<html" in full.content.decode()
    assert fragment.status_code == 200
    assert "cases/_case_results.html" in [template.name for template in fragment.templates]
    assert "<html" not in fragment.content.decode()
    assert str(case.pk) in fragment.content.decode()
    assert "HX-Request" in full.headers["Vary"]
    assert "HX-Request" in fragment.headers["Vary"]
    assert full.context["form"]["sort"].value() == "-updated"
    assert full.context["form"]["page_size"].value() == "25"


@pytest.mark.django_db
def test_case_list_exposes_the_complete_get_query_contract(
    client: Client,
    administrator: User,
    court_factory: Callable[..., Court],
) -> None:
    court = court_factory()
    client.force_login(administrator)

    response = client.get(
        list_url(),
        {
            "q": "SYN",
            "court": str(court.pk),
            "status": "active",
            "procedural_stage": "accepted",
            "acceptance_type_code": "VDS",
            "acceptance_year": "2026",
            "acceptance_date_from": "2026-01-01",
            "acceptance_date_to": "2026-12-31",
            "archive_state": "all",
            "sort": "court",
            "page": "1",
            "page_size": "50",
        },
    )

    html = response.content.decode()
    for field_name in (
        "q",
        "court",
        "status",
        "procedural_stage",
        "acceptance_type_code",
        "acceptance_year",
        "acceptance_date_from",
        "acceptance_date_to",
        "archive_state",
        "sort",
        "page_size",
    ):
        assert f'name="{field_name}"' in html
    assert 'method="get"' in html
    assert 'action="/cases/"' in html
    assert 'hx-get="/cases/"' in html
    assert 'hx-push-url="true"' in html
    assert 'hx-target="#case-results"' in html
    assert "SYN" in html


@pytest.mark.django_db
def test_case_list_is_side_effect_free_and_requires_view_permission(
    client: Client,
    administrator: User,
    user_factory: Callable[..., User],
) -> None:
    client.force_login(administrator)
    allowed = client.get(list_url())
    assert allowed.status_code == 200
    assert AuditEvent.objects.count() == 0

    outsider = user_factory(username="synthetic-case-list-outsider")
    client.force_login(outsider)
    denied = client.get(list_url())
    assert denied.status_code == 403


@pytest.mark.django_db
def test_query_state_is_preserved_in_sort_pagination_page_size_and_clear_links(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    for index in range(27):
        case_factory(internal_reference=f"SYN-PRESERVE-{index:02d}")
    client.force_login(administrator)

    response = client.get(
        list_url(),
        {"q": "SYN-PRESERVE", "status": "active", "sort": "court", "page_size": "10"},
    )

    assert response.context["next_url"].endswith(
        "q=SYN-PRESERVE&status=active&sort=court&page_size=10&page=2"
    )
    assert "q=SYN-PRESERVE" in response.context["sortable_columns"]["court"]["url"]
    assert "status=active" in response.context["sortable_columns"]["court"]["url"]
    assert dict(response.context["page_size_urls"])[50].endswith(
        "q=SYN-PRESERVE&status=active&sort=court&page_size=50"
    )
    clear_search = next(
        item["clear_url"] for item in response.context["active_filters"] if item["name"] == "q"
    )
    assert "q=" not in clear_search
    assert "status=active" in clear_search


@pytest.mark.django_db
def test_invalid_query_and_empty_states_are_distinct(
    client: Client,
    administrator: User,
) -> None:
    client.force_login(administrator)

    initial = client.get(list_url())
    filtered = client.get(list_url(), {"q": "SYN-NO-MATCH"})
    invalid = client.get(list_url(), {"page_size": "999"}, HTTP_HX_REQUEST="true")

    assert gettext("No cases yet") in initial.content.decode()
    assert gettext("No cases match these filters") in filtered.content.decode()
    assert invalid.status_code == 422
    assert gettext("Check the case-list filters") in invalid.content.decode()
    assert "999" not in invalid.content.decode()


@pytest.mark.django_db
def test_case_list_does_not_expose_relationship_or_identity_fields_in_the_url_contract(
    client: Client,
    administrator: User,
) -> None:
    client.force_login(administrator)
    html = client.get(list_url()).content.decode()

    for sensitive_name in (
        "identity_document_number",
        "registration_number",
        "case_address",
        "case_contact",
        "participant",
        "representative_entity",
    ):
        assert f'name="{sensitive_name}"' not in html


@pytest.mark.django_db
def test_case_list_principal_matrix(
    client: Client,
    administrator: User,
    user_factory: Callable[..., User],
) -> None:
    anonymous = client.get(list_url())
    assert anonymous.status_code == 302
    assert anonymous.headers["Location"] == "/login/?next=/cases/"

    inactive = user_factory(username="synthetic-list-inactive", is_active=False)
    inactive.groups.add(Group.objects.get(name=ADMINISTRATOR_GROUP_NAME))
    client.force_login(inactive)
    assert client.get(list_url()).status_code == 302

    direct_permission = user_factory(username="synthetic-list-direct-permission")
    direct_permission.user_permissions.add(Permission.objects.get(codename="view_cases"))
    client.force_login(direct_permission)
    assert client.get(list_url()).status_code == 403

    superuser = user_factory(username="synthetic-list-superuser", is_superuser=True, is_staff=True)
    client.force_login(superuser)
    assert client.get(list_url()).status_code == 200


@pytest.mark.django_db
def test_administrator_missing_view_permission_is_forbidden(
    client: Client,
    administrator: User,
) -> None:
    group = Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)
    group.permissions.remove(Permission.objects.get(codename="view_cases"))
    client.force_login(administrator)

    assert client.get(list_url()).status_code == 403


@pytest.mark.django_db
def test_expired_htmx_case_list_request_contains_no_case_data(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case_factory(internal_reference="SYN-EXPIRY-SECRET")
    client.force_login(administrator)
    session = client.session
    expired = (timezone.now() - timedelta(hours=9)).timestamp()
    session[SESSION_STARTED_AT_KEY] = expired
    session[SESSION_LAST_ACTIVITY_KEY] = expired
    session.save()

    response = client.get(list_url(), HTTP_HX_REQUEST="true")

    assert response.status_code == 401
    assert response.content == b""
    assert response.headers["HX-Redirect"].startswith("/session-expired/")
    assert "SYN-EXPIRY-SECRET" not in response.content.decode()

    client.force_login(administrator)
    assert client.get(list_url()).status_code == 200


@pytest.mark.django_db
def test_case_list_query_budget_does_not_grow_per_row(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    for index in range(25):
        case_factory(internal_reference=f"SYN-BUDGET-{index:02d}")
    client.force_login(administrator)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(list_url())

    assert response.status_code == 200
    assert len(queries) == 18, [query["sql"] for query in queries]
