from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import cast

import pytest
from django.contrib.auth.models import Permission, User
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import seed_administrator_permissions
from apps.cases.models import CaseRecord
from apps.documents.generation_artifacts import GenerationAttemptFailed, generate_artifact
from apps.documents.generation_reservations import (
    issue_generation_idempotency_key,
    reserve_generation,
)
from apps.documents.models import DocumentDraft, GeneratedDocument
from apps.documents.tests.test_generation_rendering import _template_bytes
from apps.documents.tests.test_generation_workflow_views import _ready_workflow
from tests.factories import CaseRecordFactory

pytestmark = pytest.mark.django_db


def _actor(user_factory: object, *, username: str = "history-admin") -> User:
    actor = cast(Callable[..., User], user_factory)(username=username)
    actor.groups.add(seed_administrator_permissions())
    return actor


def _history_url(case_id: object) -> str:
    return reverse("documents:case-generation-history", args=[case_id])


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
        correlation_id="history-test",
    )
    try:
        return generate_artifact(
            actor=actor,
            attempt_id=reserved.pk,
            correlation_id="history-test",
        )
    except GenerationAttemptFailed as error:
        return GeneratedDocument.objects.get(pk=error.attempt_id)


@pytest.mark.parametrize("htmx", [False, True])
def test_history_lists_safe_metadata_newest_first_for_full_and_fragment(
    client: Client,
    user_factory: object,
    htmx: bool,
) -> None:
    actor = _actor(user_factory)
    failed = _attempt(actor, fail=True)
    package = _template_bytes()
    storages["private"].save(failed.template_version.storage_key, ContentFile(package))
    generated = reserve_generation(
        actor=actor,
        case_id=failed.case_id,
        draft_id=failed.source_draft_id,
        type_key=failed.type_key,
        schema_version=failed.schema_version,
        expected_case_revision=failed.case_revision,
        expected_draft_revision=failed.draft_revision,
        expected_template_id=failed.template_version_id,
        idempotency_key=issue_generation_idempotency_key(),
        correlation_id="history-test-2",
    )
    generated = generate_artifact(
        actor=actor,
        attempt_id=generated.pk,
        correlation_id="history-test-2",
    )
    client.force_login(actor)

    response = client.get(
        _history_url(failed.case_id),
        headers={"HX-Request": "true"} if htmx else {},
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert body.index(str(generated.pk)) < body.index(str(failed.pk))
    assert generated.output_filename in body
    assert failed.get_failure_category_display() in body
    assert failed.template_version.version in body
    assert failed.schema_version in body
    assert actor.get_username() in body
    assert "data-generation-history" in body
    assert "HX-Request" in response.headers["Vary"]
    assert "no-store" in response.headers["Cache-Control"]
    assert "input_snapshot" not in body
    assert "resolved_values_snapshot" not in body
    assert failed.template_version.storage_key not in body
    assert generated.output_storage_key not in body


def test_history_is_empty_without_creating_generation_state(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    case, _draft, _template = _ready_workflow(actor)
    client.force_login(actor)

    response = client.get(_history_url(case.pk))

    assert response.status_code == 200
    assert "data-generation-history-empty" in response.content.decode()
    assert not GeneratedDocument.objects.exists()


def test_archived_case_history_remains_readable_without_retry_action(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    failed = _attempt(actor, fail=True)
    case = failed.case
    case.status = case.Status.ARCHIVED
    case.archived_by = actor
    case.archived_at = timezone.now()
    case.archive_reason = "Synthetic archive"
    case.save(update_fields=("status", "archived_by", "archived_at", "archive_reason"))
    client.force_login(actor)

    response = client.get(_history_url(case.pk))

    assert response.status_code == 200
    assert str(failed.pk) in response.content.decode()
    assert "data-generation-retry-form" not in response.content.decode()


def test_history_requires_permission_and_does_not_disclose_another_case(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    attempt = _attempt(actor)
    other_actor = _actor(user_factory, username="history-other-admin")
    other_case = cast(
        CaseRecord,
        CaseRecordFactory(created_by=other_actor, last_edited_by=other_actor),
    )
    permission = Permission.objects.get(codename="view_document_history")
    actor.groups.get(name="Administrator").permissions.remove(permission)
    actor = User.objects.get(pk=actor.pk)
    client.force_login(actor)

    denied = client.get(_history_url(attempt.case_id))
    hidden = client.get(_history_url(other_case.pk))

    assert denied.status_code == 403
    assert hidden.status_code == 403
    assert other_case.internal_reference not in hidden.content.decode()


def test_history_query_count_is_bounded(
    client: Client,
    user_factory: object,
    django_assert_max_num_queries: Callable[[int], AbstractContextManager[object]],
) -> None:
    actor = _actor(user_factory)
    attempt = _attempt(actor)
    for sequence in range(4):
        reserved = reserve_generation(
            actor=actor,
            case_id=attempt.case_id,
            draft_id=attempt.source_draft_id,
            type_key=attempt.type_key,
            schema_version=attempt.schema_version,
            expected_case_revision=attempt.case_revision,
            expected_draft_revision=attempt.draft_revision,
            expected_template_id=attempt.template_version_id,
            idempotency_key=issue_generation_idempotency_key(),
            correlation_id=f"history-query-{sequence}",
        )
        generate_artifact(
            actor=actor,
            attempt_id=reserved.pk,
            correlation_id=f"history-query-{sequence}",
        )
    client.force_login(actor)

    with django_assert_max_num_queries(18):
        response = client.get(_history_url(attempt.case_id))

    assert response.status_code == 200


def test_failed_retry_is_post_only_idempotent_and_creates_a_distinct_attempt(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    failed = _attempt(actor, fail=True)
    storages["private"].save(
        failed.template_version.storage_key,
        ContentFile(_template_bytes()),
    )
    client.force_login(actor)
    page = client.get(_history_url(failed.case_id))
    retry_form = page.context["retry_forms"][failed.pk]
    payload = {
        "attempt_id": retry_form["attempt_id"].value(),
        "idempotency_key": retry_form["idempotency_key"].value(),
    }

    get_retry = client.get(reverse("documents:retry-generation", args=[failed.case_id]))
    first = client.post(
        reverse("documents:retry-generation", args=[failed.case_id]),
        payload,
        headers={"HX-Request": "true"},
    )
    duplicate = client.post(
        reverse("documents:retry-generation", args=[failed.case_id]),
        payload,
        headers={"HX-Request": "true"},
    )

    assert get_retry.status_code == 405
    assert first.status_code == duplicate.status_code == 200
    failed.refresh_from_db()
    assert failed.status == GeneratedDocument.Status.FAILED
    assert GeneratedDocument.objects.filter(case_id=failed.case_id).count() == 2
    retry = GeneratedDocument.objects.exclude(pk=failed.pk).get()
    assert retry.pk != failed.pk
    assert retry.status == GeneratedDocument.Status.GENERATED
    assert first.context["retry_attempt_id"] == duplicate.context["retry_attempt_id"] == retry.pk


def test_retry_requires_csrf_and_generate_permission(
    csrf_client: Client,
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    failed = _attempt(actor, fail=True)
    payload = {
        "attempt_id": failed.pk,
        "idempotency_key": issue_generation_idempotency_key(),
    }
    url = reverse("documents:retry-generation", args=[failed.case_id])
    csrf_client.force_login(actor)

    csrf_denied = csrf_client.post(url, payload, headers={"HX-Request": "true"})

    assert csrf_denied.status_code == 403
    assert GeneratedDocument.objects.count() == 1

    actor.groups.get(name="Administrator").permissions.remove(
        Permission.objects.get(codename="generate_documents")
    )
    actor = User.objects.get(pk=actor.pk)
    client.force_login(actor)
    permission_denied = client.post(url, payload)

    assert permission_denied.status_code == 403
    assert GeneratedDocument.objects.count() == 1


def test_retry_rejects_successful_or_cross_case_attempt_without_mutation(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    successful = _attempt(actor)
    other_actor = _actor(user_factory, username="retry-other-admin")
    other_case = cast(
        CaseRecord,
        CaseRecordFactory(created_by=other_actor, last_edited_by=other_actor),
    )
    other_draft = DocumentDraft.objects.create(
        case=other_case,
        type_key=successful.type_key,
        schema_version=successful.schema_version,
        payload={
            "title": "Other retry title",
            "notes": "Other retry notes",
            "participant_id": None,
        },
        state=DocumentDraft.State.READY,
        revision=1,
        created_by=other_actor,
        last_edited_by=other_actor,
    )
    other_reserved = reserve_generation(
        actor=other_actor,
        case_id=other_case.pk,
        draft_id=other_draft.pk,
        type_key=other_draft.type_key,
        schema_version=other_draft.schema_version,
        expected_case_revision=other_case.revision,
        expected_draft_revision=other_draft.revision,
        expected_template_id=successful.template_version_id,
        idempotency_key=issue_generation_idempotency_key(),
        correlation_id="cross-case-retry",
    )
    storages["private"].delete(successful.template_version.storage_key)
    try:
        generate_artifact(
            actor=other_actor,
            attempt_id=other_reserved.pk,
            correlation_id="cross-case-retry",
        )
    except GenerationAttemptFailed as error:
        other_failed = GeneratedDocument.objects.get(pk=error.attempt_id)
    client.force_login(actor)
    url = reverse("documents:retry-generation", args=[successful.case_id])

    successful_response = client.post(
        url,
        {"attempt_id": successful.pk, "idempotency_key": issue_generation_idempotency_key()},
    )
    cross_case_response = client.post(
        url,
        {"attempt_id": other_failed.pk, "idempotency_key": issue_generation_idempotency_key()},
    )

    assert successful_response.status_code == 404
    assert cross_case_response.status_code == 404
    assert GeneratedDocument.objects.count() == 2
