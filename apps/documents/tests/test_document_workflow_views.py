from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from django import forms
from django.contrib.auth.models import Permission, User
from django.db import DatabaseError
from django.test import Client
from django.urls import reverse

from apps.accounts.permissions import seed_administrator_permissions
from apps.cases.models import CaseRecord
from apps.documents.models import DocumentDraft, TemplateVersion
from apps.documents.registry import DocumentFormBundle, document_registry
from tests.factories import CaseRecordFactory

pytestmark = pytest.mark.django_db


def _actor(user_factory: object) -> User:
    actor = user_factory(username="synthetic-document-workflow-admin")  # type: ignore[operator]
    actor.groups.add(seed_administrator_permissions())
    return actor


def _case(actor: User, *, archived: bool = False) -> CaseRecord:
    case = cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))
    if archived:
        from django.utils import timezone

        case.status = CaseRecord.Status.ARCHIVED
        case.archived_by = actor
        case.archived_at = timezone.now()
        case.archive_reason = "Synthetic archived case"
        case.save()
    return case


def _active_template(actor: User) -> TemplateVersion:
    template = TemplateVersion.objects.create(
        type_key="synthetic-platform-test",
        version="workflow-v1",
        original_filename="synthetic.docx",
        checksum_sha256="c" * 64,
        byte_size=256,
        uploader=actor,
        approval_reference="SYN-WORKFLOW-APPROVAL",
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
    return template


def _selector_url(case: CaseRecord) -> str:
    return reverse("documents:case-document-selector", args=[case.pk])


def _draft_url(case: CaseRecord, type_key: str = "synthetic-platform-test") -> str:
    return reverse("documents:case-document-draft", args=[case.pk, type_key])


def test_selector_lists_only_enabled_types_with_active_valid_templates(
    client: Client, user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    client.force_login(actor)

    empty = client.get(_selector_url(case))
    assert empty.status_code == 200
    assert "data-document-selector-empty" in empty.content.decode()

    _active_template(actor)
    available = client.get(_selector_url(case))
    assert available.status_code == 200
    assert "SYNTHETIC-DOC" in available.content.decode()
    assert _draft_url(case) in available.content.decode()

    registration = document_registry.get("synthetic-platform-test")
    monkeypatch.setattr(document_registry, "get", lambda _key: replace(registration, enabled=False))
    monkeypatch.setattr(
        document_registry,
        "describe",
        lambda: ({"key": registration.key, "enabled": False},),
    )
    disabled = client.get(_selector_url(case))
    assert "SYNTHETIC-DOC" not in disabled.content.decode()


def test_selector_and_draft_return_full_pages_or_narrow_htmx_fragments(
    client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    _active_template(actor)
    client.force_login(actor)

    for url, full_name, fragment_name in (
        (
            _selector_url(case),
            "documents/document_selector.html",
            "documents/_document_selector.html",
        ),
        (_draft_url(case), "documents/document_draft.html", "documents/_document_draft_form.html"),
    ):
        full = client.get(url)
        fragment = client.get(url, headers={"HX-Request": "true"})
        assert full.status_code == fragment.status_code == 200
        assert full.templates[0].name == full_name
        assert fragment.templates[0].name == fragment_name
        assert "HX-Request" in full.headers["Vary"]
        assert "HX-Request" in fragment.headers["Vary"]
        assert "no-store" in full.headers["Cache-Control"]
        assert 'hx-history="false"' in fragment.content.decode()


def test_unknown_inactive_and_invalid_type_versions_are_unavailable(
    client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    client.force_login(actor)
    assert client.get(_draft_url(case, "unknown-type")).status_code == 404

    invalid = TemplateVersion.objects.create(
        type_key="synthetic-platform-test",
        version="invalid-v1",
        original_filename="synthetic.docx",
        checksum_sha256="d" * 64,
        byte_size=256,
        uploader=actor,
        approval_reference="SYN-INVALID",
    )
    invalid.validation_report = {
        "schema_version": 1,
        "result": "invalid",
        "categories": ["package_invalid"],
        "counts": {},
    }
    invalid.save(update_fields=("validation_report",))
    invalid.transition_to(TemplateVersion.Status.INVALID)
    assert client.get(_draft_url(case)).status_code == 404


def test_new_existing_ready_and_draft_workflow_preserves_values(
    client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    _active_template(actor)
    client.force_login(actor)

    initial = client.get(_draft_url(case))
    assert case.matter_type in initial.content.decode()
    assert 'data-value-source="case.matter_type"' in initial.content.decode()

    invalid = client.post(_draft_url(case), {"title": "", "notes": "kept", "state": "draft"})
    assert invalid.status_code == 422
    body = invalid.content.decode()
    assert "data-error-summary" in body
    assert 'value="kept"' in body or ">kept</textarea>" in body

    created = client.post(
        _draft_url(case),
        {"title": "First draft", "notes": "Synthetic notes", "state": "ready"},
    )
    assert created.status_code == 302
    draft = DocumentDraft.objects.get(case=case)
    assert draft.state == DocumentDraft.State.READY
    assert draft.revision == 1

    loaded = client.get(_draft_url(case))
    assert "First draft" in loaded.content.decode()
    updated = client.post(
        _draft_url(case),
        {
            "title": "Reopened draft",
            "notes": "Synthetic notes",
            "state": "draft",
            "draft_id": draft.pk,
            "revision": draft.revision,
            "schema_version": draft.schema_version,
        },
    )
    assert updated.status_code == 302
    draft.refresh_from_db()
    assert draft.state == DocumentDraft.State.DRAFT
    assert draft.revision == 2


@pytest.mark.parametrize("htmx", [False, True])
def test_stale_revision_and_schema_mismatch_return_recoverable_conflicts(
    client: Client, user_factory: object, htmx: bool
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    _active_template(actor)
    client.force_login(actor)
    client.post(_draft_url(case), {"title": "Initial", "state": "draft"})
    draft = DocumentDraft.objects.get(case=case)
    headers = {"HX-Request": "true"} if htmx else {}

    for schema_version, revision in (("v2", 1), ("v1", 0)):
        response = client.post(
            _draft_url(case),
            {
                "title": "Stale value",
                "state": "draft",
                "draft_id": draft.pk,
                "revision": revision,
                "schema_version": schema_version,
            },
            headers=headers,
        )
        assert response.status_code == 409
        assert "data-draft-conflict" in response.content.decode()
        assert "Stale value" in response.content.decode()


def test_archived_case_is_readable_but_cannot_create_or_modify_drafts(
    client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    case = _case(actor, archived=True)
    _active_template(actor)
    client.force_login(actor)

    selector = client.get(_selector_url(case))
    draft = client.get(_draft_url(case))
    post = client.post(_draft_url(case), {"title": "Blocked", "state": "draft"})
    assert selector.status_code == draft.status_code == 200
    assert "data-archived-document-notice" in draft.content.decode()
    assert post.status_code == 403
    assert not DocumentDraft.objects.exists()


def test_document_views_enforce_permissions_and_csrf(
    client: Client, csrf_client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    _active_template(actor)
    group = actor.groups.get(name="Administrator")
    group.permissions.remove(Permission.objects.get(codename="view_document_drafts"))
    client.force_login(actor)
    assert client.get(_selector_url(case)).status_code == 403
    assert client.get(_draft_url(case)).status_code == 403

    actor.groups.add(seed_administrator_permissions())
    actor = User.objects.get(pk=actor.pk)
    csrf_client.force_login(actor)
    for headers in ({}, {"HX-Request": "true"}):
        response = csrf_client.post(
            _draft_url(case), {"title": "CSRF rejected", "state": "draft"}, headers=headers
        )
        assert response.status_code == 403


def test_anonymous_htmx_request_expires_without_case_content(
    client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    _active_template(actor)
    response = client.get(_draft_url(case), headers={"HX-Request": "true"})
    assert response.status_code == 302
    assert case.internal_reference not in response.content.decode()


def test_formset_validation_preserves_values_and_links_summary(
    client: Client, user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ItemForm(forms.Form):
        name = forms.CharField(max_length=50)
        detail = forms.CharField(required=False, max_length=50)

    actor = _actor(user_factory)
    case = _case(actor)
    _active_template(actor)
    client.force_login(actor)
    registration = document_registry.get("synthetic-platform-test")
    item_formset = cast(Any, forms.formset_factory(ItemForm, extra=0))
    patched = replace(
        registration,
        form_provider=lambda: DocumentFormBundle(
            registration.form_provider().form_class, (item_formset,)
        ),
    )
    monkeypatch.setattr(document_registry, "get", lambda _key: patched)

    response = client.post(
        _draft_url(case),
        {
            "title": "Formset draft",
            "state": "draft",
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-name": "",
            "form-0-detail": "Kept repeated value",
        },
    )

    assert response.status_code == 422
    body = response.content.decode()
    assert 'href="#id_form-0-name"' in body
    assert "Kept repeated value" in body

    valid = client.post(
        _draft_url(case),
        {
            "title": "Formset draft",
            "state": "draft",
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-name": "Preserved row",
            "form-0-detail": "Kept repeated value",
        },
    )
    assert valid.status_code == 302


def test_database_failure_returns_recoverable_fragment_without_payload_logging(
    client: Client,
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor = _actor(user_factory)
    case = _case(actor)
    _active_template(actor)
    client.force_login(actor)
    sensitive = "SYNTHETIC-PRIVATE-DRAFT-VALUE"

    def fail_save(**_kwargs: object) -> None:
        raise DatabaseError("Synthetic unavailable database")

    monkeypatch.setattr("apps.documents.workflow_views.create_document_draft", fail_save)
    response = client.post(
        _draft_url(case),
        {"title": sensitive, "state": "draft"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 500
    assert "data-draft-server-error" in response.content.decode()
    assert sensitive in response.content.decode()
    assert sensitive not in caplog.text
