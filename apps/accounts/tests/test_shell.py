from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.http import HttpResponse
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.core.views import server_error


@pytest.fixture
def administrator_group() -> Group:
    return Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)


@pytest.fixture
def administrator(user_factory: Callable[..., User], administrator_group: Group) -> User:
    user = user_factory(username="synthetic-shell-administrator")
    user.groups.add(administrator_group)
    return user


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _authenticated_response(
    client: Client, user: User, view_name: str = "accounts:dashboard"
) -> HttpResponse:
    client.force_login(user)
    return cast(HttpResponse, client.get(reverse(view_name)))


@pytest.mark.django_db
def test_authenticated_shell_has_semantic_landmarks_and_skip_target(
    client: Client, administrator: User
) -> None:
    response = _authenticated_response(client, administrator)
    html = response.content.decode()

    assert response.status_code == 200
    assert '<a class="skip-link" href="#main-content">' in html
    assert '<header class="app-header"' in html
    assert '<nav class="primary-navigation" aria-label=' in html
    assert '<main id="main-content"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'role="alert"' in html
    assert 'aria-live="assertive"' in html
    assert 'aria-busy="false"' in html


@pytest.mark.django_db
def test_active_navigation_uses_named_django_url(client: Client, administrator: User) -> None:
    response = _authenticated_response(client, administrator, "accounts:dashboard")
    html = response.content.decode()

    assert 'data-view-name="accounts:dashboard"' in html
    assert 'aria-current="page"' in html
    assert 'data-active-view="accounts:dashboard"' in html


@pytest.mark.django_db
@pytest.mark.parametrize("principal", ["administrator", "superuser"])
def test_normal_administrator_and_superuser_see_all_authorized_navigation(
    client: Client,
    administrator: User,
    user_factory: Callable[..., User],
    principal: str,
) -> None:
    user = (
        administrator
        if principal == "administrator"
        else user_factory(username="synthetic-shell-superuser", is_staff=True, is_superuser=True)
    )

    response = _authenticated_response(client, user)
    html = response.content.decode()

    for view_name in (
        "accounts:dashboard",
        "cases:list",
        "documents:templates",
        "audit:list",
    ):
        assert f'href="{reverse(view_name)}"' in html


@pytest.mark.django_db
def test_missing_permission_hides_audit_navigation_but_server_still_denies_destination(
    client: Client,
    administrator: User,
    administrator_group: Group,
) -> None:
    audit_permission = Permission.objects.get(
        content_type__app_label="accounts", codename="view_audit"
    )
    administrator_group.permissions.remove(audit_permission)

    shell_response = _authenticated_response(client, administrator)
    audit_response = client.get(reverse("audit:list"))

    assert reverse("audit:list") not in shell_response.content.decode()
    assert audit_response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("view_name", "permission_codename"),
    [
        ("cases:list", "view_cases"),
        ("documents:templates", "view_templates"),
        ("audit:list", "view_audit"),
    ],
)
def test_placeholder_destinations_enforce_server_permissions(
    client: Client,
    administrator: User,
    administrator_group: Group,
    view_name: str,
    permission_codename: str,
) -> None:
    permission = Permission.objects.get(
        content_type__app_label="accounts", codename=permission_codename
    )
    administrator_group.permissions.remove(permission)
    client.force_login(administrator)

    response = client.get(reverse(view_name))

    assert response.status_code == 403


@pytest.mark.django_db
def test_shell_logout_is_a_csrf_protected_post_form(client: Client, administrator: User) -> None:
    response = _authenticated_response(client, administrator)
    html = response.content.decode()

    assert f'<form method="post" action="{reverse("accounts:logout")}"' in html
    assert 'name="csrfmiddlewaretoken"' in html
    assert f'href="{reverse("accounts:logout")}"' not in html


@pytest.mark.django_db
def test_full_page_and_htmx_shell_use_the_same_vietnamese_locale(
    client: Client, administrator: User
) -> None:
    client.force_login(administrator)
    full_response = client.get(reverse("accounts:dashboard"))
    htmx_response = client.get(reverse("accounts:dashboard"), headers={"HX-Request": "true"})

    assert full_response.headers["Content-Language"] == "vi"
    assert htmx_response.headers["Content-Language"] == "vi"
    assert '<html lang="vi"' in full_response.content.decode()
    assert "Bảng điều khiển" in full_response.content.decode()
    assert "Bảng điều khiển" in htmx_response.content.decode()


@pytest.mark.django_db
def test_shell_marks_sensitive_htmx_history_as_disabled(
    client: Client, administrator: User
) -> None:
    html = _authenticated_response(client, administrator).content.decode()

    assert 'hx-history="false"' in html
    assert 'historyEnabled":false' in html
    assert "localStorage" not in html
    assert "sessionStorage" not in html


@pytest.mark.django_db
def test_theme_and_drawer_markup_exposes_accessible_ephemeral_controls(
    client: Client, administrator: User
) -> None:
    html = _authenticated_response(client, administrator).content.decode()

    assert 'x-data="applicationShell"' in html
    assert 'aria-controls="primary-navigation"' in html
    assert 'x-bind:aria-expanded="drawerOpen"' in html
    assert 'x-bind:inert="!drawerOpen && !desktopNavigation"' in html
    assert 'x-bind:hidden="!drawerOpen"' in html
    assert 'x-ref="drawer"' in html
    assert 'x-on:keydown.escape.window="closeDrawer"' in html
    assert 'x-on:keydown.tab="trapDrawerFocus"' in html
    assert 'x-data="themeControls"' in html
    assert 'x-on:click="chooseTheme' in html
    assert "vds-theme" not in html


@pytest.mark.django_db
def test_shell_exposes_htmx_driven_busy_state(client: Client, administrator: User) -> None:
    html = _authenticated_response(client, administrator).content.decode()

    assert 'id="global-loading"' in html
    assert 'aria-busy="false"' in html
    javascript = (PROJECT_ROOT / "static_src" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'document.addEventListener("htmx:beforeRequest"' in javascript
    assert 'document.addEventListener("htmx:afterRequest"' in javascript
    assert 'mainContent.setAttribute("aria-busy", String(isBusy))' in javascript


@pytest.mark.django_db
def test_shell_scripts_are_local_and_csp_compatible(client: Client, administrator: User) -> None:
    html = _authenticated_response(client, administrator).content.decode()

    assert "https://" not in html
    assert "http://" not in html
    assert "<script>" not in html
    assert "'unsafe-inline'" not in html
    assert "'unsafe-eval'" not in html
    assert "/static/vendor/htmx/htmx.min.js" in html
    assert "/static/vendor/alpine/alpine.csp.min.js" in html
    assert "/static/js/app.js" in html


@pytest.mark.django_db
def test_generic_error_pages_and_session_state_disclose_no_internal_details(
    client: Client, administrator: User, administrator_group: Group
) -> None:
    cases_permission = Permission.objects.get(
        content_type__app_label="accounts", codename="view_cases"
    )
    administrator_group.permissions.remove(cases_permission)
    client.force_login(administrator)
    forbidden = client.get(reverse("cases:list"))
    not_found = client.get("/synthetic-internal-identifier/")
    expired = client.get(reverse("accounts:session-expired"))
    request = RequestFactory().get("/")
    server_failure = server_error(request)

    assert forbidden.status_code == 403
    assert not_found.status_code == 404
    assert server_failure.status_code == 500
    for response in (forbidden, not_found, expired, server_failure):
        body = response.content.decode()
        assert "synthetic-internal-identifier" not in body
        assert "Traceback" not in body
        assert "Exception" not in body
        assert "settings." not in body
        assert "password" not in body.lower()


def test_server_error_view_uses_only_the_generic_template(monkeypatch: pytest.MonkeyPatch) -> None:
    render_mock = Mock()
    monkeypatch.setattr("apps.core.views.render", render_mock)
    request = RequestFactory().get("/")

    server_error(request)

    render_mock.assert_called_once_with(request, "errors/500.html", status=500)
