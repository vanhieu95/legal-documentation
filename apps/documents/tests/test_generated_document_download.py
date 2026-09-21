from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest
from django.contrib.auth.models import Permission, User
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import Client
from django.urls import reverse

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.models import AuditEvent
from apps.documents.downloads import build_content_disposition
from apps.documents.generation_artifacts import GenerationAttemptFailed, generate_artifact
from apps.documents.generation_reservations import (
    issue_generation_idempotency_key,
    reserve_generation,
)
from apps.documents.models import GeneratedDocument
from apps.documents.tests.test_generation_rendering import _template_bytes
from apps.documents.tests.test_generation_workflow_views import _ready_workflow

pytestmark = pytest.mark.django_db

DOWNLOAD_ACTION = "document_generation.downloaded"


def _actor(user_factory: object, *, username: str = "download-admin") -> User:
    actor = cast(Callable[..., User], user_factory)(username=username)
    actor.groups.add(seed_administrator_permissions())
    return actor


def _attempt(actor: User, *, fail: bool = False) -> GeneratedDocument:
    case, draft, template = _ready_workflow(actor)
    if fail:
        storages["private"].delete(template.storage_key)
    reserved = reserve_generation(
        actor=actor,
        case_id=case.pk,
        draft_id=draft.pk,
        type_key=draft.type_key,
        schema_version=draft.schema_version,
        expected_case_revision=case.revision,
        expected_draft_revision=draft.revision,
        expected_template_id=template.pk,
        idempotency_key=issue_generation_idempotency_key(),
        correlation_id="download-test",
    )
    try:
        return generate_artifact(
            actor=actor,
            attempt_id=reserved.pk,
            correlation_id="download-test",
        )
    except GenerationAttemptFailed as error:
        return GeneratedDocument.objects.get(pk=error.attempt_id)


def _url(attempt: GeneratedDocument) -> str:
    return reverse("documents:generated-document-download", args=[attempt.pk])


def _body(response: Any) -> bytes:
    return b"".join(response.streaming_content)


def test_authorized_download_returns_exact_stored_bytes_headers_and_success_audit(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    attempt = _attempt(actor)
    with storages["private"].open(attempt.output_storage_key, "rb") as source:
        expected = source.read()
    client.force_login(actor)

    response = client.get(_url(attempt))

    assert response.status_code == 200
    assert _body(response) == expected
    assert response.headers["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.headers["Content-Length"] == str(len(expected))
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert {"no-store", "private"}.issubset(
        {directive.strip() for directive in response.headers["Cache-Control"].split(",")}
    )
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Content-Disposition"].startswith("attachment; filename=")
    assert "filename*=UTF-8''" in response.headers["Content-Disposition"]
    event = AuditEvent.objects.get(action=DOWNLOAD_ACTION, target_id=str(attempt.pk))
    assert event.actor == actor
    assert event.outcome == "success"
    assert event.metadata == {}


def test_download_denies_anonymous_and_missing_permission_and_audits_each_attempt(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    attempt = _attempt(actor)

    anonymous = client.get(_url(attempt))

    actor.groups.get(name="Administrator").permissions.remove(
        Permission.objects.get(codename="download_documents")
    )
    actor = User.objects.get(pk=actor.pk)
    client.force_login(actor)
    forbidden = client.get(_url(attempt))

    assert anonymous.status_code == 302
    assert forbidden.status_code == 403
    events = AuditEvent.objects.filter(action=DOWNLOAD_ACTION, target_id=str(attempt.pk)).order_by(
        "occurred_at"
    )
    assert [event.outcome for event in events] == ["denied", "denied"]
    assert events[0].is_system_actor is True
    assert events[1].actor == actor


def test_download_hides_guessed_and_failed_attempts_and_records_denial(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    failed = _attempt(actor, fail=True)
    client.force_login(actor)
    guessed_id = "11111111-1111-4111-8111-111111111111"

    failed_response = client.get(_url(failed))
    guessed_response = client.get(
        reverse("documents:generated-document-download", args=[guessed_id])
    )

    assert failed_response.status_code == guessed_response.status_code == 404
    events = AuditEvent.objects.filter(action=DOWNLOAD_ACTION, outcome="denied")
    assert set(events.values_list("target_id", flat=True)) == {str(failed.pk), guessed_id}


def test_download_applies_case_object_scope(
    client: Client,
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor(user_factory)
    attempt = _attempt(actor)
    client.force_login(actor)
    monkeypatch.setattr(
        "apps.documents.downloads.case_object_policy.scope_queryset",
        lambda _actor, queryset: queryset.none(),
    )

    response = client.get(_url(attempt))

    assert response.status_code == 404
    event = AuditEvent.objects.get(action=DOWNLOAD_ACTION, target_id=str(attempt.pk))
    assert event.outcome == "denied"


@pytest.mark.parametrize("failure", ["missing", "tampered-checksum", "tampered-size"])
def test_download_rejects_missing_or_changed_artifact_and_records_failure(
    client: Client,
    user_factory: object,
    failure: str,
) -> None:
    actor = _actor(user_factory)
    attempt = _attempt(actor)
    storage = storages["private"]
    if failure == "missing":
        storage.delete(attempt.output_storage_key)
    else:
        storage.delete(attempt.output_storage_key)
        package = _template_bytes()
        if failure == "tampered-checksum":
            changed_bytes = bytearray(package)
            changed_bytes[len(changed_bytes) // 2] ^= 1
            changed = bytes(changed_bytes)
        else:
            changed = package + b"tampered"
        storage.save(attempt.output_storage_key, ContentFile(changed))
    client.force_login(actor)

    response = client.get(_url(attempt))

    assert response.status_code == 404
    event = AuditEvent.objects.get(action=DOWNLOAD_ACTION, target_id=str(attempt.pk))
    assert event.outcome == "failure"
    assert event.metadata == {}


def test_htmx_header_does_not_change_download_response(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    attempt = _attempt(actor)
    client.force_login(actor)

    response = client.get(_url(attempt), headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert response.streaming is True
    assert "HX-Request" not in response.headers.get("Vary", "")


def test_content_disposition_has_safe_ascii_fallback_and_utf8_filename() -> None:
    header = build_content_disposition("Đề nghị tổng hợp.docx")

    assert header.startswith("attachment; filename=\"De nghi tong hop.docx\"; filename*=UTF-8''")
    assert "%C4%90%E1%BB%81%20ngh%E1%BB%8B%20t%E1%BB%95ng%20h%E1%BB%A3p.docx" in header
