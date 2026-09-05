from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.test import Client
from django.urls import reverse

from apps.accounts.forms import (
    AUDIT_REASON_INACTIVE_ACCOUNT,
    AUDIT_REASON_INVALID_CREDENTIALS,
    AUDIT_REASON_NOT_ADMINISTRATOR,
)
from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.accounts.policies import ApplicationPermission, service_permission_required
from apps.accounts.services import (
    activate_account,
    change_password,
    complete_password_reset,
    deactivate_account,
    set_group_memberships,
    set_user_permissions,
)
from apps.accounts.sessions import (
    ABSOLUTE_SESSION_LIMIT,
    INACTIVITY_SESSION_LIMIT,
)
from apps.accounts.tests.test_authentication import PASSWORD, login
from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.models import AuditEvent

CORRELATION_ID = "synthetic-audit-correlation-001"
SUBMITTED_USERNAME = "synthetic-submitted-username"
SUBMITTED_PASSWORD = "synthetic-submitted-password"
PROTECTED_CONTENT = "Administration area"


@pytest.fixture
def administrator_group() -> Group:
    return Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)


@pytest.fixture
def administrator(user_factory: Callable[..., User], administrator_group: Group) -> User:
    user = user_factory(username="synthetic-audit-administrator", password=PASSWORD)
    user.groups.add(administrator_group)
    return user


def _assert_no_sensitive_payload(event: AuditEvent) -> None:
    serialized = json.dumps(
        {
            "changed_fields": event.changed_fields,
            "metadata": event.metadata,
            "target_id": event.target_id,
            "correlation_id": event.correlation_id,
            "action": event.action,
            "outcome": event.outcome,
        }
    ).lower()
    for prohibited in (
        SUBMITTED_PASSWORD.lower(),
        SUBMITTED_USERNAME.lower(),
        "csrf",
        "session_key",
        "request body",
        PROTECTED_CONTENT.lower(),
    ):
        assert prohibited not in serialized


@pytest.mark.django_db
def test_successful_administrator_login_records_one_audit_event(
    client: Client, administrator: User
) -> None:
    response = client.post(
        reverse("accounts:login"),
        {"username": administrator.username, "password": PASSWORD},
        HTTP_X_CORRELATION_ID=CORRELATION_ID,
    )

    assert response.status_code == 302
    events = AuditEvent.objects.filter(action=AuditAction.IDENTITY_LOGIN)
    assert events.count() == 1
    event = events.get()
    assert event.outcome == AuditOutcome.SUCCESS
    assert event.actor == administrator
    assert event.correlation_id == CORRELATION_ID
    _assert_no_sensitive_payload(event)


@pytest.mark.django_db
def test_successful_superuser_login_records_one_audit_event(
    client: Client, user_factory: Callable[..., User]
) -> None:
    superuser = user_factory(
        username="synthetic-audit-superuser",
        password=PASSWORD,
        is_staff=True,
        is_superuser=True,
    )

    response = login(client, superuser.username)

    assert response.status_code == 302
    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_LOGIN)
    assert event.outcome == AuditOutcome.SUCCESS
    assert event.actor == superuser
    _assert_no_sensitive_payload(event)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("username", "password", "reason_code", "outcome"),
    [
        ("unknown-account", PASSWORD, AUDIT_REASON_INVALID_CREDENTIALS, AuditOutcome.FAILURE),
        (
            "synthetic-invalid-password-user",
            "wrong-password",
            AUDIT_REASON_INVALID_CREDENTIALS,
            AuditOutcome.FAILURE,
        ),
    ],
)
def test_failed_login_records_safe_audit_event(
    client: Client,
    user_factory: Callable[..., User],
    username: str,
    password: str,
    reason_code: str,
    outcome: str,
) -> None:
    if username == "synthetic-invalid-password-user":
        user_factory(username=username, password=PASSWORD)

    response = client.post(
        reverse("accounts:login"),
        {"username": username, "password": password},
        HTTP_X_CORRELATION_ID=CORRELATION_ID,
    )

    assert response.status_code == 200
    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_LOGIN)
    assert event.outcome == outcome
    assert event.metadata["reason_code"] == reason_code
    assert event.is_system_actor is True
    _assert_no_sensitive_payload(event)


@pytest.mark.django_db
def test_inactive_account_login_records_denied_audit_event(
    client: Client, user_factory: Callable[..., User], administrator_group: Group
) -> None:
    inactive_user = user_factory(username="synthetic-inactive-audit-user", password=PASSWORD)
    inactive_user.groups.add(administrator_group)
    inactive_user.is_active = False
    inactive_user.save(update_fields=["is_active"])

    response = client.post(
        reverse("accounts:login"),
        {"username": inactive_user.username, "password": PASSWORD},
        HTTP_X_CORRELATION_ID=CORRELATION_ID,
    )

    assert response.status_code == 200
    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_LOGIN)
    assert event.outcome == AuditOutcome.DENIED
    assert event.metadata["reason_code"] == AUDIT_REASON_INACTIVE_ACCOUNT
    _assert_no_sensitive_payload(event)


@pytest.mark.django_db
def test_non_administrator_login_records_denied_audit_event(
    client: Client, user_factory: Callable[..., User]
) -> None:
    non_administrator = user_factory(username="synthetic-non-admin-audit-user", password=PASSWORD)

    response = client.post(
        reverse("accounts:login"),
        {"username": non_administrator.username, "password": PASSWORD},
        HTTP_X_CORRELATION_ID=CORRELATION_ID,
    )

    assert response.status_code == 200
    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_LOGIN)
    assert event.outcome == AuditOutcome.DENIED
    assert event.metadata["reason_code"] == AUDIT_REASON_NOT_ADMINISTRATOR
    _assert_no_sensitive_payload(event)


@pytest.mark.django_db
def test_logout_records_one_audit_event(client: Client, administrator: User) -> None:
    login(client, administrator.username)

    response = client.post(
        reverse("accounts:logout"),
        HTTP_X_CORRELATION_ID=CORRELATION_ID,
    )

    assert response.status_code == 302
    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_LOGOUT)
    assert event.outcome == AuditOutcome.SUCCESS
    assert event.actor == administrator
    assert event.correlation_id == CORRELATION_ID


@pytest.mark.django_db
def test_inactivity_expiration_records_one_session_audit_event(
    client: Client, administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr("apps.accounts.sessions.current_time", lambda: start)
    login(client, administrator.username)

    expired = start + INACTIVITY_SESSION_LIMIT
    monkeypatch.setattr("apps.accounts.sessions.current_time", lambda: expired)
    response = client.get(
        reverse("accounts:dashboard"),
        HTTP_X_CORRELATION_ID=CORRELATION_ID,
    )

    assert response.status_code == 302
    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_SESSION_EXPIRED)
    assert event.metadata["reason_code"] == "inactivity"
    assert event.target_type == AuditTargetType.SESSION
    assert event.correlation_id == CORRELATION_ID
    _assert_no_sensitive_payload(event)


@pytest.mark.django_db
def test_absolute_session_expiration_records_one_session_audit_event(
    client: Client, administrator: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr("apps.accounts.sessions.current_time", lambda: start)
    login(client, administrator.username)

    expired = start + ABSOLUTE_SESSION_LIMIT
    monkeypatch.setattr("apps.accounts.sessions.current_time", lambda: expired)
    response = client.get(
        reverse("accounts:dashboard"),
        HTTP_X_CORRELATION_ID=CORRELATION_ID,
    )

    assert response.status_code == 302
    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_SESSION_EXPIRED)
    assert event.metadata["reason_code"] == "absolute"


@pytest.mark.django_db
def test_password_change_records_audit_event(administrator: User) -> None:
    change_password(
        actor=administrator,
        user=administrator,
        new_password="changed-password-123",
        correlation_id=CORRELATION_ID,
    )

    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_PASSWORD_CHANGED)
    assert event.actor == administrator
    assert event.changed_fields == ["password"]
    _assert_no_sensitive_payload(event)


@pytest.mark.django_db
def test_password_reset_records_audit_event(administrator: User) -> None:
    complete_password_reset(
        user=administrator,
        new_password="reset-password-456",
        correlation_id=CORRELATION_ID,
    )

    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_PASSWORD_RESET)
    assert event.is_system_actor is True
    assert event.changed_fields == ["password"]


@pytest.mark.django_db
def test_account_activation_and_deactivation_record_audit_events(
    user_factory: Callable[..., User],
    administrator: User,
) -> None:
    superuser = user_factory(username="synthetic-audit-superuser", is_superuser=True, is_staff=True)
    target = user_factory(username="synthetic-target-account", is_active=False)

    activate_account(actor=superuser, user=target, correlation_id=CORRELATION_ID)
    deactivate_account(actor=superuser, user=target, correlation_id=CORRELATION_ID)

    activated = AuditEvent.objects.get(action=AuditAction.IDENTITY_ACCOUNT_ACTIVATED)
    deactivated = AuditEvent.objects.get(action=AuditAction.IDENTITY_ACCOUNT_DEACTIVATED)
    assert activated.changed_fields == ["is_active"]
    assert deactivated.changed_fields == ["is_active"]


@pytest.mark.django_db
def test_group_and_permission_changes_record_audit_events(
    user_factory: Callable[..., User],
    administrator_group: Group,
) -> None:
    superuser = user_factory(
        username="synthetic-audit-superuser-2",
        is_superuser=True,
        is_staff=True,
    )
    target = user_factory(username="synthetic-target-permissions")
    permission = administrator_group.permissions.first()
    assert permission is not None

    set_group_memberships(
        actor=superuser,
        user=target,
        groups=[administrator_group],
        correlation_id=CORRELATION_ID,
    )
    set_user_permissions(
        actor=superuser,
        user=target,
        permissions=[permission],
        correlation_id=CORRELATION_ID,
    )

    assert AuditEvent.objects.filter(action=AuditAction.IDENTITY_GROUP_CHANGED).count() == 1
    assert AuditEvent.objects.filter(action=AuditAction.IDENTITY_PERMISSION_CHANGED).count() == 1


@pytest.mark.django_db
def test_unauthorized_protected_page_records_access_denied_event(
    client: Client,
    user_factory: Callable[..., User],
    administrator_group: Group,
) -> None:
    restricted_admin = user_factory(username="synthetic-restricted-audit-admin", password=PASSWORD)
    restricted_admin.groups.add(administrator_group)
    restricted_admin.user_permissions.clear()
    administrator_group.permissions.remove(
        administrator_group.permissions.get(codename="view_cases")
    )
    login(client, restricted_admin.username)

    response = client.get(
        reverse("accounts:dashboard"),
        HTTP_X_CORRELATION_ID=CORRELATION_ID,
    )

    assert response.status_code == 403
    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_ACCESS_DENIED)
    assert event.outcome == AuditOutcome.DENIED
    assert event.metadata["permission"] == ApplicationPermission.VIEW_CASES
    assert event.metadata["transport"] == "full_page"
    _assert_no_sensitive_payload(event)


@pytest.mark.django_db
def test_unauthorized_htmx_request_records_access_denied_event(
    client: Client,
    user_factory: Callable[..., User],
    administrator_group: Group,
) -> None:
    restricted_admin = user_factory(username="synthetic-restricted-htmx-admin", password=PASSWORD)
    restricted_admin.groups.add(administrator_group)
    restricted_admin.user_permissions.clear()
    administrator_group.permissions.remove(
        administrator_group.permissions.get(codename="view_cases")
    )
    login(client, restricted_admin.username)

    response = client.get(
        reverse("accounts:dashboard"),
        HTTP_HX_REQUEST="true",
        HTTP_X_CORRELATION_ID=CORRELATION_ID,
    )

    assert response.status_code == 403
    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_ACCESS_DENIED)
    assert event.metadata["transport"] == "htmx"


@pytest.mark.django_db
def test_unauthorized_service_call_records_access_denied_event(
    user_factory: Callable[..., User],
    administrator_group: Group,
) -> None:
    restricted_admin = user_factory(username="synthetic-service-denied-admin", password=PASSWORD)
    restricted_admin.groups.add(administrator_group)
    restricted_admin.user_permissions.clear()
    administrator_group.permissions.remove(
        administrator_group.permissions.get(codename="view_templates")
    )

    @service_permission_required(ApplicationPermission.VIEW_TEMPLATES)
    def protected_service(*, actor: User, correlation_id: str) -> str:
        return "protected"

    with pytest.raises(PermissionDenied):
        protected_service(actor=restricted_admin, correlation_id=CORRELATION_ID)

    event = AuditEvent.objects.get(action=AuditAction.IDENTITY_ACCESS_DENIED)
    assert event.metadata["permission"] == ApplicationPermission.VIEW_TEMPLATES


@pytest.mark.django_db
def test_password_change_audit_rolls_back_with_outer_transaction(administrator: User) -> None:
    with pytest.raises(PermissionDenied):
        with transaction.atomic():
            change_password(
                actor=administrator,
                user=administrator,
                new_password="rolled-back-password-123",
                correlation_id=CORRELATION_ID,
            )
            raise PermissionDenied("synthetic rollback")

    assert not AuditEvent.objects.filter(action=AuditAction.IDENTITY_PASSWORD_CHANGED).exists()


@pytest.mark.django_db
def test_login_failure_does_not_duplicate_audit_events(
    client: Client,
) -> None:
    client.post(
        reverse("accounts:login"),
        {"username": "missing-user", "password": PASSWORD},
    )
    assert AuditEvent.objects.filter(action=AuditAction.IDENTITY_LOGIN).count() == 1
