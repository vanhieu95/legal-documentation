from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.contrib.auth.models import Group, User
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.accounts.services import change_password, complete_password_reset
from apps.accounts.sessions import (
    ABSOLUTE_SESSION_LIMIT,
    INACTIVITY_SESSION_LIMIT,
    SESSION_LAST_ACTIVITY_KEY,
    SESSION_STARTED_AT_KEY,
    SessionExpiryReason,
    invalidate_user_sessions,
    notify_session_expired,
    safe_local_destination,
)
from apps.accounts.tests.test_authentication import PASSWORD, login

START = datetime(2026, 1, 1, tzinfo=UTC)
PROTECTED_CONTENT = "Administration area"


@pytest.fixture
def administrator_group() -> Group:
    return Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)


@pytest.fixture
def administrator(user_factory: object, administrator_group: Group) -> User:
    assert callable(user_factory)
    user = user_factory(username="synthetic-session-administrator", password=PASSWORD)
    user.groups.add(administrator_group)
    return user


def _set_clock(monkeypatch: pytest.MonkeyPatch, current: datetime) -> None:
    monkeypatch.setattr("apps.accounts.sessions.current_time", lambda: current)


def _login_at(
    client: Client,
    administrator: User,
    monkeypatch: pytest.MonkeyPatch,
    current: datetime = START,
) -> None:
    _set_clock(monkeypatch, current)
    response = login(client, administrator.username)
    assert response.status_code == 302


def _set_session_times(client: Client, *, started_at: datetime, last_activity: datetime) -> None:
    session = client.session
    session[SESSION_STARTED_AT_KEY] = started_at.timestamp()
    session[SESSION_LAST_ACTIVITY_KEY] = last_activity.timestamp()
    session.save()


@pytest.mark.django_db
def test_request_immediately_before_inactivity_limit_is_allowed_and_refreshes_activity(
    client: Client, administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_at(client, administrator, monkeypatch)
    current = START + INACTIVITY_SESSION_LIMIT - timedelta(microseconds=1)
    _set_clock(monkeypatch, current)

    response = client.get(reverse("accounts:dashboard"))

    assert response.status_code == 200
    assert client.session[SESSION_LAST_ACTIVITY_KEY] == current.timestamp()


@pytest.mark.django_db
def test_request_exactly_at_inactivity_limit_expires(
    client: Client, administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_at(client, administrator, monkeypatch)
    _set_clock(monkeypatch, START + INACTIVITY_SESSION_LIMIT)

    response = client.get(reverse("accounts:dashboard"))

    assert response.status_code == 302
    assert response.headers["Location"].startswith(reverse("accounts:session-expired"))
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_request_immediately_before_absolute_limit_is_allowed(
    client: Client, administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_at(client, administrator, monkeypatch)
    current = START + ABSOLUTE_SESSION_LIMIT - timedelta(microseconds=1)
    _set_session_times(client, started_at=START, last_activity=current - timedelta(minutes=1))
    _set_clock(monkeypatch, current)

    response = client.get(reverse("accounts:dashboard"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_request_exactly_at_absolute_limit_expires(
    client: Client, administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_at(client, administrator, monkeypatch)
    current = START + ABSOLUTE_SESSION_LIMIT
    _set_session_times(client, started_at=START, last_activity=current - timedelta(minutes=1))
    _set_clock(monkeypatch, current)

    response = client.get(reverse("accounts:dashboard"))

    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_activity_refreshes_inactivity_but_never_extends_absolute_deadline(
    client: Client, administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_at(client, administrator, monkeypatch)
    first_activity = START + timedelta(minutes=29)
    _set_clock(monkeypatch, first_activity)
    assert client.get(reverse("accounts:dashboard")).status_code == 200

    second_activity = first_activity + timedelta(minutes=29)
    _set_clock(monkeypatch, second_activity)
    assert client.get(reverse("accounts:dashboard")).status_code == 200
    assert client.session[SESSION_STARTED_AT_KEY] == START.timestamp()

    _set_session_times(
        client,
        started_at=START,
        last_activity=START + ABSOLUTE_SESSION_LIMIT - timedelta(minutes=1),
    )
    _set_clock(monkeypatch, START + ABSOLUTE_SESSION_LIMIT)
    assert client.get(reverse("accounts:dashboard")).status_code == 302


@pytest.mark.django_db
def test_concurrent_sessions_have_independent_activity_deadlines(
    administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_client = Client()
    second_client = Client()
    _login_at(first_client, administrator, monkeypatch)
    _login_at(second_client, administrator, monkeypatch)

    _set_clock(monkeypatch, START + timedelta(minutes=20))
    assert first_client.get(reverse("accounts:dashboard")).status_code == 200
    _set_clock(monkeypatch, START + timedelta(minutes=35))

    assert first_client.get(reverse("accounts:dashboard")).status_code == 200
    assert second_client.get(reverse("accounts:dashboard")).status_code == 302


@pytest.mark.django_db
def test_user_session_invalidation_removes_all_target_sessions_only(
    administrator: User,
    administrator_group: Group,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_user = User.objects.create_user(username="synthetic-other-user", password=PASSWORD)
    other_user.groups.add(administrator_group)
    target_clients = [Client(), Client()]
    other_client = Client()
    for target_client in target_clients:
        _login_at(target_client, administrator, monkeypatch)
    _login_at(other_client, other_user, monkeypatch)

    removed = invalidate_user_sessions(administrator.pk)

    assert removed == 2
    assert all("_auth_user_id" not in target_client.session for target_client in target_clients)
    assert other_client.session["_auth_user_id"] == str(other_user.pk)


@pytest.mark.django_db
def test_password_change_and_reset_invalidate_all_sessions(
    administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    change_clients = [Client(), Client()]
    for change_client in change_clients:
        _login_at(change_client, administrator, monkeypatch)
    change_session_keys = [client.session.session_key for client in change_clients]

    change_password(actor=administrator, user=administrator, new_password="changed-password-123")
    assert not Session.objects.filter(session_key__in=change_session_keys)

    reset_clients = [Client(), Client()]
    _set_clock(monkeypatch, START + timedelta(minutes=1))
    for reset_client in reset_clients:
        response = login(reset_client, administrator.username, "changed-password-123")
        assert response.status_code == 302
    reset_session_keys = [client.session.session_key for client in reset_clients]
    complete_password_reset(user=administrator, new_password="reset-password-456")
    assert not Session.objects.filter(session_key__in=reset_session_keys)


@pytest.mark.django_db
def test_user_cannot_change_another_users_password(
    administrator: User, user_factory: object
) -> None:
    assert callable(user_factory)
    other_user = user_factory(username="synthetic-password-target", password=PASSWORD)

    with pytest.raises(PermissionDenied):
        change_password(actor=administrator, user=other_user, new_password="other-password-123")

    assert other_user.check_password(PASSWORD)


@pytest.mark.django_db
def test_expired_normal_request_is_data_free_and_does_not_execute_view(
    client: Client,
    administrator: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login_at(client, administrator, monkeypatch)
    render_mock = Mock(side_effect=AssertionError("protected view executed"))
    monkeypatch.setattr("apps.accounts.views.render", render_mock)
    _set_clock(monkeypatch, START + INACTIVITY_SESSION_LIMIT)

    response = client.get(reverse("accounts:dashboard"))

    assert response.status_code == 302
    assert PROTECTED_CONTENT not in response.content.decode()
    render_mock.assert_not_called()


@pytest.mark.django_db
def test_expired_htmx_request_has_empty_body_and_full_page_redirect_header(
    client: Client, administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login_at(client, administrator, monkeypatch)
    _set_clock(monkeypatch, START + INACTIVITY_SESSION_LIMIT)

    response = client.get(
        reverse("accounts:dashboard"),
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 401
    assert response.content == b""
    assert response.headers["HX-Redirect"].startswith(reverse("accounts:session-expired"))
    assert PROTECTED_CONTENT not in response.content.decode()
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_expired_unsafe_request_without_csrf_is_rejected_before_reauthentication(
    csrf_client: Client, administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf_client.force_login(administrator)
    _set_session_times(csrf_client, started_at=START, last_activity=START)
    _set_clock(monkeypatch, START + INACTIVITY_SESSION_LIMIT)

    response = csrf_client.post(reverse("accounts:logout"))

    assert response.status_code == 403
    assert PROTECTED_CONTENT not in response.content.decode()


@pytest.mark.django_db
def test_expired_unsafe_request_with_valid_csrf_uses_data_free_reauthentication(
    csrf_client: Client, administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf_client.force_login(administrator)
    dashboard_response = csrf_client.get(reverse("accounts:dashboard"))
    csrf_token = dashboard_response.cookies["csrftoken"].value
    _set_session_times(csrf_client, started_at=START, last_activity=START)
    _set_clock(monkeypatch, START + INACTIVITY_SESSION_LIMIT)

    response = csrf_client.post(
        reverse("accounts:logout"),
        {"csrfmiddlewaretoken": csrf_token},
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith(reverse("accounts:session-expired"))
    assert response.content == b""
    assert "_auth_user_id" not in csrf_client.session


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("/dashboard/?page=2", "/dashboard/?page=2"),
        ("https://example.invalid/collect", None),
        ("//example.invalid/collect", None),
        ("\\\\example.invalid/collect", None),
        ("\x00/dashboard/", None),
    ],
)
def test_reauthentication_destination_accepts_only_safe_local_urls(
    candidate: str, expected: str | None
) -> None:
    from django.test import RequestFactory

    request = RequestFactory().get("/", secure=True, HTTP_HOST="testserver")
    assert safe_local_destination(request, candidate) == expected


@pytest.mark.django_db
def test_session_expired_page_preserves_only_validated_destination(client: Client) -> None:
    safe_response = client.get(reverse("accounts:session-expired"), {"next": "/dashboard/"})
    hostile_response = client.get(
        reverse("accounts:session-expired"), {"next": "//example.invalid/collect"}
    )

    assert safe_response.status_code == 200
    assert "next=%2Fdashboard%2F" in safe_response.content.decode()
    assert "example.invalid" not in hostile_response.content.decode()
    assert PROTECTED_CONTENT not in safe_response.content.decode()


def test_production_session_cookie_and_backend_are_secure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/synthetic")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "app.example.invalid")
    monkeypatch.setenv("DJANGO_CSRF_TRUSTED_ORIGINS", "https://app.example.invalid")
    monkeypatch.setenv("DJANGO_PRIVATE_STORAGE_ROOT", str(tmp_path / "private"))
    monkeypatch.setenv("DJANGO_STATIC_ROOT", str(tmp_path / "static"))
    monkeypatch.setenv(
        "DJANGO_SECRET_KEY", "synthetic-production-secret-with-fifty-characters-0001"
    )
    from config.settings import base, production

    assert base.SESSION_ENGINE == "django.contrib.sessions.backends.db"
    assert production.SESSION_COOKIE_SECURE is True
    assert base.SESSION_COOKIE_HTTPONLY is True
    assert base.SESSION_COOKIE_SAMESITE == "Lax"
    assert base.SESSION_COOKIE_DOMAIN is None
    assert production.SECURE_SSL_REDIRECT is True


def test_session_cleanup_runbook_documents_daily_clearsessions() -> None:
    runbook = Path("docs/operations/session-management.md").read_text(encoding="utf-8")

    assert "clearsessions" in runbook
    assert "daily" in runbook.lower()
    assert "expired" in runbook.lower()


def test_expiry_reason_contract_is_ready_for_audit_integration() -> None:
    assert set(SessionExpiryReason) == {
        SessionExpiryReason.INACTIVITY,
        SessionExpiryReason.ABSOLUTE,
    }
    notify_session_expired(user_id=1, reason=SessionExpiryReason.INACTIVITY)
