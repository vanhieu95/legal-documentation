from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import reverse

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME

PASSWORD = "synthetic-test-password"
GENERIC_FAILURE = "Không thể đăng nhập bằng thông tin đã cung cấp."
PROTECTED_CONTENT = "Khu vực quản trị"


@pytest.fixture
def administrator_group() -> Group:
    return Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)


@pytest.fixture
def administrator(user_factory: Callable[..., User], administrator_group: Group) -> User:
    user = user_factory(username="synthetic-login-administrator", password=PASSWORD)
    user.groups.add(administrator_group)
    return user


def login(client: Client, username: str, password: str = PASSWORD, **data: str) -> Any:
    return client.post(
        reverse("accounts:login"),
        {"username": username, "password": password, **data},
    )


@pytest.mark.django_db
@pytest.mark.parametrize("principal", ["administrator", "superuser"])
def test_active_authorized_principal_can_login(
    client: Client,
    principal: str,
    administrator: User,
    user_factory: Callable[..., User],
) -> None:
    user = (
        administrator
        if principal == "administrator"
        else user_factory(
            username="synthetic-login-superuser",
            password=PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
    )

    response = login(client, user.username)

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("accounts:dashboard")
    assert client.session["_auth_user_id"] == str(user.pk)


@pytest.mark.django_db
def test_successful_login_rotates_the_existing_session_key(
    client: Client, administrator: User
) -> None:
    session = client.session
    session["synthetic-nonsensitive-marker"] = "preserved"
    session.save()
    old_session_key = session.session_key

    response = login(client, administrator.username)

    assert response.status_code == 302
    assert client.session.session_key != old_session_key
    assert client.session["synthetic-nonsensitive-marker"] == "preserved"
    assert old_session_key is not None
    assert not Session.objects.filter(session_key=old_session_key).exists()


@pytest.mark.django_db
def test_failed_principals_receive_identical_generic_data_free_response(
    client: Client,
    user_factory: Callable[..., User],
) -> None:
    inactive = user_factory(username="synthetic-inactive-login", password=PASSWORD, is_active=False)
    non_administrator = user_factory(username="synthetic-login-outsider", password=PASSWORD)
    scenarios = (
        ("synthetic-unknown-login", PASSWORD),
        (non_administrator.username, PASSWORD),
        (inactive.username, PASSWORD),
        ("synthetic-login-outsider", "synthetic-wrong-password"),
    )

    bodies: list[str] = []
    for username, password in scenarios:
        response = login(client, username, password)
        body = response.content.decode()
        bodies.append(body)
        assert response.status_code == 200
        assert GENERIC_FAILURE in body
        assert username not in body
        assert password not in body
        assert PROTECTED_CONTENT not in body
        assert "_auth_user_id" not in client.session

    assert all(body.count(GENERIC_FAILURE) == 1 for body in bodies)


@pytest.mark.django_db
def test_safe_local_next_is_used_after_login(client: Client, administrator: User) -> None:
    destination = reverse("component-gallery") + "?page=2"

    response = login(client, administrator.username, next=destination)

    assert response.status_code == 302
    assert response.headers["Location"] == destination


@pytest.mark.django_db
@pytest.mark.parametrize(
    "unsafe_destination",
    [
        "https://example.invalid/collect",
        "//example.invalid/collect",
        "//[malformed",
        "http:///malformed",
        "\\\\example.invalid/collect",
        "\x00/dashboard/",
        "\t/dashboard/",
    ],
)
def test_unsafe_next_falls_back_to_dashboard(
    client: Client, administrator: User, unsafe_destination: str
) -> None:
    response = login(client, administrator.username, next=unsafe_destination)

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("accounts:dashboard")


@pytest.mark.django_db
def test_anonymous_login_and_protected_placeholder_redirect(client: Client) -> None:
    login_response = client.get(reverse("accounts:login"))
    protected_response = client.get(reverse("accounts:dashboard"))

    assert login_response.status_code == 200
    assert protected_response.status_code == 302
    assert protected_response.headers["Location"] == (
        f"{settings.LOGIN_URL}?next={reverse('accounts:dashboard')}"
    )
    assert PROTECTED_CONTENT not in protected_response.content.decode()


@pytest.mark.django_db
def test_forced_non_administrator_session_cannot_view_protected_placeholder(
    client: Client, user_factory: Callable[..., User]
) -> None:
    client.force_login(user_factory(username="synthetic-forced-outsider"))

    response = client.get(reverse("accounts:dashboard"))

    assert response.status_code == 403
    assert PROTECTED_CONTENT not in response.content.decode()


@pytest.mark.django_db
def test_post_logout_flushes_session_and_old_cookie_cannot_be_reused(
    client: Client, administrator: User
) -> None:
    login(client, administrator.username)
    old_session_key = client.session.session_key
    assert old_session_key is not None

    response = client.post(reverse("accounts:logout"))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("accounts:login")
    assert not Session.objects.filter(session_key=old_session_key).exists()
    replay_client = Client()
    replay_client.cookies[settings.SESSION_COOKIE_NAME] = old_session_key
    replay_response = replay_client.get(reverse("accounts:dashboard"))
    assert replay_response.status_code == 302
    assert PROTECTED_CONTENT not in replay_response.content.decode()


@pytest.mark.django_db
def test_get_logout_is_rejected(client: Client, administrator: User) -> None:
    client.force_login(administrator)

    response = client.get(reverse("accounts:logout"))

    assert response.status_code == 405
    assert client.session["_auth_user_id"] == str(administrator.pk)


@pytest.mark.django_db
@pytest.mark.parametrize("htmx", [False, True])
def test_logout_rejects_missing_csrf_token(
    csrf_client: Client, administrator: User, htmx: bool
) -> None:
    csrf_client.force_login(administrator)
    headers = {"HX-Request": "true"} if htmx else {}

    response = csrf_client.post(reverse("accounts:logout"), headers=headers)

    assert response.status_code == 403
    assert csrf_client.session["_auth_user_id"] == str(administrator.pk)
    assert PROTECTED_CONTENT not in response.content.decode()


@pytest.mark.django_db
def test_login_rejects_missing_csrf_token(csrf_client: Client, administrator: User) -> None:
    response = csrf_client.post(
        reverse("accounts:login"),
        {"username": administrator.username, "password": PASSWORD},
    )

    assert response.status_code == 403
    assert "_auth_user_id" not in csrf_client.session


@pytest.mark.django_db
def test_authentication_pages_and_actions_are_not_cacheable(
    client: Client, administrator: User
) -> None:
    responses = [
        client.get(reverse("accounts:login")),
        login(client, "synthetic-unknown-cache-user"),
    ]
    client.force_login(administrator)
    responses.append(client.post(reverse("accounts:logout")))

    for response in responses:
        assert "no-store" in response.headers["Cache-Control"]


@pytest.mark.django_db
def test_login_page_is_vietnamese_and_does_not_offer_credential_persistence(client: Client) -> None:
    response = client.get(reverse("accounts:login"))
    body = response.content.decode()

    assert response.headers["Content-Language"] == "vi"
    assert '<html lang="vi"' in body
    assert "Tên đăng nhập" in body
    assert "Mật khẩu" in body
    assert 'autocomplete="username"' in body
    assert 'autocomplete="current-password"' in body
    assert "remember" not in body.lower()
    assert 'type="password"' in body
    assert 'value="synthetic' not in body
