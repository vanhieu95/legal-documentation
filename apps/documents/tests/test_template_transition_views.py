from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth.models import Permission, User
from django.db import close_old_connections, connection
from django.test import Client
from django.urls import reverse

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.documents.models import TemplateVersion

pytestmark = pytest.mark.django_db


def _actor(user_factory: object) -> User:
    actor = user_factory(username="synthetic-transition-view-admin")  # type: ignore[operator]
    actor.groups.add(seed_administrator_permissions())
    return actor


def _version(actor: User, version: str = "ui-v1") -> TemplateVersion:
    template = TemplateVersion.objects.create(
        type_key="synthetic-platform-test",
        version=version,
        original_filename="private-name.docx",
        checksum_sha256="b" * 64,
        byte_size=256,
        uploader=actor,
        approval_reference="APPROVAL-UI-1",
    )
    template.validation_report = {
        "schema_version": 1,
        "result": "valid",
        "categories": [],
        "counts": {"synthetic_renders": 2},
    }
    template.save(update_fields=("validation_report",))
    template.transition_to(TemplateVersion.Status.VALID)
    return template


def _url(action: str, template: TemplateVersion) -> str:
    return reverse(
        f"documents:template-{action}",
        args=[template.type_key, template.pk],
    )


@pytest.mark.parametrize("action", ["activate", "deactivate"])
def test_confirmation_is_full_page_or_htmx_fragment_and_names_safe_identity(
    client: Client, user_factory: object, action: str
) -> None:
    actor = _actor(user_factory)
    template = _version(actor)
    if action == "deactivate":
        template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)
    client.force_login(actor)

    full = client.get(_url(action, template))
    fragment = client.get(_url(action, template), headers={"HX-Request": "true"})

    assert full.status_code == fragment.status_code == 200
    assert full.templates[0].name == "documents/template_transition.html"
    assert fragment.templates[0].name == "documents/_template_transition_form.html"
    for response in (full, fragment):
        body = response.content.decode()
        assert "SYNTHETIC-DOC" in body and "ui-v1" in body
        assert template.storage_key not in body
        assert template.original_filename not in body
        assert 'name="csrfmiddlewaretoken"' in body
        assert 'name="expected_status"' in body
        assert 'name="expected_active_id"' in body


def test_post_activates_then_deactivates_with_normal_redirect_fallback(
    client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    template = _version(actor)
    client.force_login(actor)

    activated = client.post(
        _url("activate", template),
        {"expected_status": TemplateVersion.Status.VALID},
    )
    template.refresh_from_db()
    assert activated.status_code == 302
    assert template.status == TemplateVersion.Status.ACTIVE

    deactivated = client.post(
        _url("deactivate", template),
        {
            "expected_status": TemplateVersion.Status.ACTIVE,
            "expected_active_id": str(template.pk),
        },
    )
    template.refresh_from_db()
    assert deactivated.status_code == 302
    assert template.status == TemplateVersion.Status.INACTIVE
    assert AuditEvent.objects.filter(action=AuditAction.TEMPLATE_ACTIVATED).count() == 1
    assert AuditEvent.objects.filter(action=AuditAction.TEMPLATE_DEACTIVATED).count() == 1


def test_stale_htmx_transition_returns_swappable_409(client: Client, user_factory: object) -> None:
    actor = _actor(user_factory)
    template = _version(actor)
    client.force_login(actor)
    template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)

    response = client.post(
        _url("activate", template),
        {"expected_status": TemplateVersion.Status.VALID},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 409
    assert response.templates[0].name == "documents/_template_transition_form.html"
    assert "data-conflict-summary" in response.content.decode()
    assert "data-template-dialog-close" in response.content.decode()
    assert reverse("documents:template-list") in response.content.decode()
    assert "HX-Request" in response.headers["Vary"]


@pytest.mark.parametrize("action", ["activate", "deactivate"])
@pytest.mark.parametrize("htmx", [False, True])
def test_transition_posts_reject_missing_csrf(
    csrf_client: Client, user_factory: object, action: str, htmx: bool
) -> None:
    actor = _actor(user_factory)
    template = _version(actor)
    if action == "deactivate":
        template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)
    csrf_client.force_login(actor)

    response = csrf_client.post(
        _url(action, template),
        {"expected_status": template.status},
        headers={"HX-Request": "true"} if htmx else {},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("htmx", [False, True])
def test_malformed_confirmation_returns_validation_errors(
    client: Client, user_factory: object, htmx: bool
) -> None:
    actor = _actor(user_factory)
    template = _version(actor)
    client.force_login(actor)

    response = client.post(
        _url("activate", template),
        {"expected_status": "not-a-state", "expected_active_id": "not-a-uuid"},
        headers={"HX-Request": "true"} if htmx else {},
    )

    assert response.status_code == (422 if htmx else 200)
    assert "errorlist" in response.content.decode()


def test_activate_and_deactivate_views_enforce_distinct_permissions(
    client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    template = _version(actor)
    group = actor.groups.get(name="Administrator")
    group.permissions.remove(Permission.objects.get(codename="deactivate_templates"))
    client.force_login(actor)

    assert client.get(_url("activate", template)).status_code == 200
    assert client.get(_url("deactivate", template)).status_code == 403


def test_deactivate_view_does_not_require_activate_permission(
    client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    template = _version(actor)
    template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)
    group = actor.groups.get(name="Administrator")
    group.permissions.remove(Permission.objects.get(codename="activate_templates"))
    client.force_login(actor)

    assert client.get(_url("activate", template)).status_code == 403
    assert client.get(_url("deactivate", template)).status_code == 200


@pytest.mark.parametrize("action", ["activate", "deactivate"])
def test_transition_rejects_unsupported_mutation_methods(
    action: str, client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    template = _version(actor)
    client.force_login(actor)

    assert client.put(_url(action, template)).status_code == 405


@pytest.mark.parametrize("action", ["activate", "deactivate"])
def test_safe_get_does_not_mutate_template(
    action: str, client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    template = _version(actor)
    if action == "deactivate":
        template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)
    status = template.status
    client.force_login(actor)

    assert client.get(_url(action, template)).status_code == 200
    template.refresh_from_db()
    assert template.status == status


@pytest.mark.parametrize(
    ("action", "status"),
    [
        ("activate", TemplateVersion.Status.INVALID),
        ("deactivate", TemplateVersion.Status.VALID),
    ],
)
def test_confirmation_rejects_non_candidate_state_with_recoverable_conflict(
    action: str,
    status: str,
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    template = _version(actor)
    if status == TemplateVersion.Status.INVALID:
        template = TemplateVersion.objects.create(
            type_key="synthetic-platform-test",
            version="ui-invalid",
            original_filename="private-name.docx",
            checksum_sha256="e" * 64,
            byte_size=256,
            uploader=actor,
            approval_reference="APPROVAL-UI-INVALID",
        )
        template.validation_report = {
            "schema_version": 1,
            "result": "invalid",
            "categories": ["not_zip"],
            "counts": {"not_zip": 1},
        }
        template.save(update_fields=("validation_report",))
        template.transition_to(TemplateVersion.Status.INVALID)
    client.force_login(actor)

    response = client.get(_url(action, template))

    assert response.status_code == 409
    assert "data-conflict-summary" in response.content.decode()


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_htmx_activations_return_success_and_conflict(
    user_factory: Callable[..., User], monkeypatch: pytest.MonkeyPatch
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL concurrency profile.")
    actor = _actor(user_factory)
    first = _version(actor)
    second = _version(actor, "ui-v2")
    barrier = Barrier(2)
    from apps.documents import services

    acquire_lock = services._acquire_type_transition_lock

    def synchronized_lock(type_key: str) -> None:
        barrier.wait()
        acquire_lock(type_key)

    monkeypatch.setattr(services, "_acquire_type_transition_lock", synchronized_lock)

    def submit(template: TemplateVersion) -> int:
        close_old_connections()
        thread_actor = User.objects.get(pk=actor.pk)
        thread_client = Client()
        thread_client.force_login(thread_actor)
        try:
            response = thread_client.post(
                _url("activate", template),
                {"expected_status": TemplateVersion.Status.VALID, "expected_active_id": ""},
                headers={"HX-Request": "true"},
            )
            return response.status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(submit, (first, second)))

    assert sorted(statuses) == [204, 409]
    assert TemplateVersion.objects.filter(status=TemplateVersion.Status.ACTIVE).count() == 1
