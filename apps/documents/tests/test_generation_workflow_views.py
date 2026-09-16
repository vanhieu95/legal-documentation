from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, storages
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.actions import AuditAction, AuditOutcome
from apps.audit.models import AuditEvent
from apps.cases.models import CaseRecord
from apps.documents.models import DocumentDraft, GeneratedDocument, TemplateVersion
from apps.documents.storage_keys import build_template_storage_key
from apps.documents.tests.test_generation_rendering import _template_bytes
from apps.documents.tests.test_template_versions import template_values
from tests.factories import CaseRecordFactory

pytestmark = pytest.mark.django_db


class _StorageHandlerCache(Protocol):
    _storages: dict[str, Storage]


class _ContextResponse(Protocol):
    context: Any


@pytest.fixture(autouse=True)
def _isolated_private_storage(settings: Any, tmp_path: Path) -> None:
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"
    cast(_StorageHandlerCache, storages)._storages.clear()


def _actor(user_factory: object) -> User:
    actor = cast(Callable[..., User], user_factory)(username="generation-workflow-admin")
    actor.groups.add(seed_administrator_permissions())
    return actor


def _ready_workflow(actor: User) -> tuple[CaseRecord, DocumentDraft, TemplateVersion]:
    case = cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))
    package = _template_bytes()
    template_key = build_template_storage_key("synthetic-platform-test", "workflow-generation-v1")
    assert storages["private"].save(template_key, ContentFile(package)) == template_key
    template = TemplateVersion.objects.create(
        **template_values(
            uploader=actor,
            version="workflow-generation-v1",
            storage_key=template_key,
            checksum_sha256=hashlib.sha256(package).hexdigest(),
            byte_size=len(package),
        )
    )
    template.validation_report = {
        "schema_version": 1,
        "result": "valid",
        "categories": [],
        "counts": {"synthetic_renders": 2},
    }
    template.save(update_fields=("validation_report",))
    template.transition_to(TemplateVersion.Status.VALID)
    template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)
    draft = DocumentDraft.objects.create(
        case=case,
        type_key="synthetic-platform-test",
        schema_version="v1",
        payload={
            "title": "Synthetic generated title",
            "notes": "Synthetic generated notes",
            "participant_id": None,
        },
        state=DocumentDraft.State.READY,
        revision=1,
        created_by=actor,
        last_edited_by=actor,
    )
    return case, draft, template


def _draft_url(case: CaseRecord) -> str:
    return reverse(
        "documents:case-document-draft",
        args=[case.pk, "synthetic-platform-test"],
    )


def _generation_payload(response: _ContextResponse) -> dict[str, object]:
    context = response.context
    generation_form = context["generation_form"]
    return {
        "intent": "generate",
        "draft_id": generation_form["draft_id"].value(),
        "expected_case_revision": generation_form["expected_case_revision"].value(),
        "expected_draft_revision": generation_form["expected_draft_revision"].value(),
        "schema_version": generation_form["schema_version"].value(),
        "expected_template_id": generation_form["expected_template_id"].value(),
        "idempotency_key": generation_form["idempotency_key"].value(),
        "confirmed": "on",
    }


def test_ready_draft_exposes_named_confirmation_with_a_fresh_opaque_token(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    case, draft, template = _ready_workflow(actor)
    client.force_login(actor)

    response = client.get(_draft_url(case))

    assert response.status_code == 200
    assert "data-generation-confirmation" in response.content.decode()
    payload = _generation_payload(response)
    assert payload["draft_id"] == str(draft.pk)
    assert payload["expected_template_id"] == str(template.pk)
    assert len(cast(str, payload["idempotency_key"])) == 43
    assert case.internal_reference in response.content.decode()
    assert template.version in response.content.decode()


@pytest.mark.parametrize("htmx", [False, True])
def test_confirmed_generation_is_synchronous_and_idempotent(
    client: Client,
    user_factory: object,
    htmx: bool,
) -> None:
    actor = _actor(user_factory)
    case, _draft, _template = _ready_workflow(actor)
    client.force_login(actor)
    payload = _generation_payload(client.get(_draft_url(case)))
    headers = {"HX-Request": "true"} if htmx else {}

    first = client.post(_draft_url(case), payload, headers=headers)
    duplicate = client.post(_draft_url(case), payload, headers=headers)

    assert first.status_code == duplicate.status_code == 200
    assert "data-generation-result" in first.content.decode()
    assert "data-generation-success" in first.content.decode()
    assert first.context["attempt"].pk == duplicate.context["attempt"].pk
    assert GeneratedDocument.objects.count() == 1
    attempt = GeneratedDocument.objects.get()
    assert attempt.status == GeneratedDocument.Status.GENERATED
    assert storages["private"].exists(attempt.output_storage_key)
    assert AuditEvent.objects.filter(action=AuditAction.DOCUMENT_GENERATION_RESERVED).count() == 1
    assert AuditEvent.objects.filter(action=AuditAction.DOCUMENT_GENERATION_SUCCEEDED).count() == 1
    assert "no-store" in first.headers["Cache-Control"]
    assert "HX-Request" in first.headers["Vary"]


@pytest.mark.parametrize("htmx", [False, True])
def test_invalid_confirmation_preserves_ready_draft_without_an_attempt(
    client: Client,
    user_factory: object,
    htmx: bool,
) -> None:
    actor = _actor(user_factory)
    case, draft, _template = _ready_workflow(actor)
    client.force_login(actor)
    payload = _generation_payload(client.get(_draft_url(case)))
    payload.pop("confirmed")

    response = client.post(
        _draft_url(case),
        payload,
        headers={"HX-Request": "true"} if htmx else {},
    )

    assert response.status_code == 422
    assert "data-generation-confirmation" in response.content.decode()
    assert "data-error-summary" in response.content.decode()
    assert not GeneratedDocument.objects.exists()
    draft.refresh_from_db()
    assert draft.state == DocumentDraft.State.READY


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("expected_case_revision", 999),
        ("expected_draft_revision", 999),
        ("expected_template_id", uuid4()),
    ],
)
def test_stale_confirmation_returns_a_reload_conflict_without_generation(
    client: Client,
    user_factory: object,
    field: str,
    replacement: object,
) -> None:
    actor = _actor(user_factory)
    case, _draft, _template = _ready_workflow(actor)
    client.force_login(actor)
    payload = _generation_payload(client.get(_draft_url(case)))
    payload[field] = replacement

    response = client.post(_draft_url(case), payload, headers={"HX-Request": "true"})

    assert response.status_code == 409
    body = response.content.decode()
    assert "data-draft-conflict" in body
    assert "data-generation-confirmation" not in body
    assert not GeneratedDocument.objects.exists()


def test_template_becoming_unavailable_returns_recoverable_conflict(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    case, _draft, template = _ready_workflow(actor)
    client.force_login(actor)
    payload = _generation_payload(client.get(_draft_url(case)))
    template.transition_to(TemplateVersion.Status.INACTIVE)

    response = client.post(_draft_url(case), payload)

    assert response.status_code == 409
    assert "data-generation-unavailable" in response.content.decode()
    assert not GeneratedDocument.objects.exists()


def test_generation_permission_is_enforced_and_hides_confirmation(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    case, _draft, _template = _ready_workflow(actor)
    client.force_login(actor)
    payload = _generation_payload(client.get(_draft_url(case)))
    group = actor.groups.get(name="Administrator")
    group.permissions.remove(Permission.objects.get(codename="generate_documents"))
    actor = User.objects.get(pk=actor.pk)
    client.force_login(actor)

    page = client.get(_draft_url(case))
    denied = client.post(_draft_url(case), payload)

    assert "data-generation-confirmation" not in page.content.decode()
    assert denied.status_code == 403
    assert not GeneratedDocument.objects.exists()
    assert AuditEvent.objects.filter(
        action=AuditAction.IDENTITY_ACCESS_DENIED,
        outcome=AuditOutcome.DENIED,
    ).exists()


@pytest.mark.parametrize("htmx", [False, True])
def test_generation_post_requires_csrf(
    csrf_client: Client,
    user_factory: object,
    htmx: bool,
) -> None:
    actor = _actor(user_factory)
    case, draft, template = _ready_workflow(actor)
    csrf_client.force_login(actor)
    payload = {
        "intent": "generate",
        "draft_id": draft.pk,
        "expected_case_revision": case.revision,
        "expected_draft_revision": draft.revision,
        "schema_version": draft.schema_version,
        "expected_template_id": template.pk,
        "idempotency_key": "a" * 43,
        "confirmed": "on",
    }

    response = csrf_client.post(
        _draft_url(case),
        payload,
        headers={"HX-Request": "true"} if htmx else {},
    )

    assert response.status_code == 403
    assert not GeneratedDocument.objects.exists()


@pytest.mark.parametrize("htmx", [False, True])
def test_generation_failure_is_durable_and_preserves_the_ready_draft(
    client: Client,
    user_factory: object,
    htmx: bool,
) -> None:
    actor = _actor(user_factory)
    case, draft, template = _ready_workflow(actor)
    client.force_login(actor)
    payload = _generation_payload(client.get(_draft_url(case)))
    storages["private"].delete(template.storage_key)
    headers = {"HX-Request": "true"} if htmx else {}

    response = client.post(_draft_url(case), payload, headers=headers)
    duplicate = client.post(_draft_url(case), payload, headers=headers)

    assert response.status_code == duplicate.status_code == 200
    assert "data-generation-failure" in response.content.decode()
    assert attempt_failure_label() in response.content.decode()
    assert response.context["attempt"].pk == duplicate.context["attempt"].pk
    attempt = GeneratedDocument.objects.get()
    assert attempt.status == GeneratedDocument.Status.FAILED
    assert not attempt.output_storage_key
    draft.refresh_from_db()
    assert draft.state == DocumentDraft.State.READY


def attempt_failure_label() -> str:
    return str(GeneratedDocument.FailureCategory.STORAGE_ERROR.label)


def test_archived_case_cannot_expose_or_submit_generation_confirmation(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    case, _draft, _template = _ready_workflow(actor)
    client.force_login(actor)
    payload = _generation_payload(client.get(_draft_url(case)))
    case.status = CaseRecord.Status.ARCHIVED
    case.archived_by = actor
    case.archived_at = timezone.now()
    case.archive_reason = "Synthetic archive"
    case.save(update_fields=("status", "archived_by", "archived_at", "archive_reason"))

    page = client.get(_draft_url(case))
    response = client.post(_draft_url(case), payload)

    assert "data-generation-confirmation" not in page.content.decode()
    assert response.status_code == 403
    assert not GeneratedDocument.objects.exists()


def test_anonymous_generation_request_redirects_without_sensitive_content(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    case, draft, template = _ready_workflow(actor)
    response = client.post(
        _draft_url(case),
        {
            "intent": "generate",
            "draft_id": draft.pk,
            "expected_case_revision": case.revision,
            "expected_draft_revision": draft.revision,
            "schema_version": draft.schema_version,
            "expected_template_id": template.pk,
            "idempotency_key": "a" * 43,
            "confirmed": "on",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 302
    assert case.internal_reference not in response.content.decode()
    assert not GeneratedDocument.objects.exists()
