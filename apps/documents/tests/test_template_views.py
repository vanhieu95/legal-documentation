from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import Permission, User
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.accounts.permissions import seed_administrator_permissions
from apps.documents.limits import MAX_TEMPLATE_BYTES
from apps.documents.models import TemplateVersion
from apps.documents.tests.docx_fixtures import minimal_docx, word_document

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _isolated_private_storage(settings: Any, tmp_path: Path) -> None:
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"
    storages._storages.clear()  # type: ignore[attr-defined]


def _actor(user_factory: object) -> User:
    actor = user_factory(username="synthetic-template-view-admin")  # type: ignore[operator]
    actor.groups.add(seed_administrator_permissions())
    return actor


def _package() -> bytes:
    return minimal_docx(
        entries={
            "word/document.xml": word_document(
                (("{{ document.title }}",), ("{{ document.notes|default('') }}",))
            )
        }
    )


def _post_data(package: bytes | None = None, **overrides: str) -> dict[str, object]:
    values: dict[str, object] = {
        "version": "v1.0",
        "approval_reference": "SYNTHETIC-APPROVAL-UI-001",
        "template_file": SimpleUploadedFile(
            "../../unsafe-template.docx",
            package if package is not None else _package(),
            content_type="application/octet-stream",
        ),
    }
    values.update(overrides)
    return values


def test_template_list_returns_full_page_and_narrow_htmx_fragment(
    client: Client, user_factory: object
) -> None:
    client.force_login(_actor(user_factory))
    url = reverse("documents:template-list")

    full = client.get(url)
    fragment = client.get(url, headers={"HX-Request": "true"})

    assert full.status_code == fragment.status_code == 200
    assert full.templates[0].name == "documents/template_list.html"
    assert fragment.templates[0].name == "documents/_template_list.html"
    assert "HX-Request" in full.headers["Vary"]
    assert "HX-Request" in fragment.headers["Vary"]
    assert "SYNTHETIC-DOC" in full.content.decode()
    upload_url = reverse("documents:template-upload", args=["synthetic-platform-test"])
    assert upload_url in full.content.decode()


def test_template_list_shows_empty_state(client: Client, user_factory: object) -> None:
    client.force_login(_actor(user_factory))

    response = client.get(reverse("documents:template-list"))

    assert response.status_code == 200
    assert "data-template-empty-state" in response.content.decode()


def test_template_list_shows_empty_unavailable_valid_and_invalid_states(
    client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    client.force_login(actor)
    base = {
        "type_key": "synthetic-platform-test",
        "original_filename": "synthetic.docx",
        "checksum_sha256": "a" * 64,
        "byte_size": 10,
        "uploader": actor,
        "approval_reference": "SYNTHETIC-APPROVAL",
    }
    valid = TemplateVersion.objects.create(version="valid-1", **base)
    valid.validation_report = {
        "schema_version": 1,
        "result": "valid",
        "categories": [],
        "counts": {"synthetic_renders": 2},
    }
    valid.save(update_fields=("validation_report",))
    valid.transition_to(TemplateVersion.Status.VALID)
    invalid = TemplateVersion.objects.create(version="invalid-1", **base)
    invalid.validation_report = {
        "schema_version": 1,
        "result": "invalid",
        "categories": ["not_zip"],
        "counts": {"not_zip": 1},
    }
    invalid.save(update_fields=("validation_report",))
    invalid.transition_to(TemplateVersion.Status.INVALID)

    response = client.get(reverse("documents:template-list"))
    body = response.content.decode()

    assert response.status_code == 200
    assert "valid-1" in body and "invalid-1" in body
    assert "not_zip" not in body
    assert valid.storage_key not in body and invalid.storage_key not in body
    assert "data-activation-candidate" in body


def test_upload_page_returns_full_page_and_htmx_workflow_fragment(
    client: Client, user_factory: object
) -> None:
    client.force_login(_actor(user_factory))
    url = reverse("documents:template-upload", args=["synthetic-platform-test"])

    full = client.get(url)
    fragment = client.get(url, headers={"HX-Request": "true"})

    assert full.status_code == fragment.status_code == 200
    assert full.templates[0].name == "documents/template_upload.html"
    assert fragment.templates[0].name == "documents/_template_upload_workflow.html"
    assert "HX-Request" in full.headers["Vary"]
    assert "HX-Request" in fragment.headers["Vary"]
    body = full.content.decode()
    assert 'enctype="multipart/form-data"' in body
    assert 'name="csrfmiddlewaretoken"' in body
    assert 'aria-live="polite"' in body
    assert 'class="htmx-indicator' in body
    assert "/activate/" not in body


def test_valid_upload_uses_service_and_never_activates(
    client: Client, user_factory: object
) -> None:
    client.force_login(_actor(user_factory))
    url = reverse("documents:template-upload", args=["synthetic-platform-test"])

    response = client.post(url, _post_data(), follow=True)

    assert response.status_code == 200
    template = TemplateVersion.objects.get(version="v1.0")
    assert template.status == TemplateVersion.Status.VALID
    assert TemplateVersion.objects.filter(status=TemplateVersion.Status.ACTIVE).count() == 0
    assert "data-activation-candidate" in response.content.decode()


def test_invalid_upload_is_durable_and_htmx_returns_safe_success_fragment(
    client: Client, user_factory: object
) -> None:
    client.force_login(_actor(user_factory))
    url = reverse("documents:template-upload", args=["synthetic-platform-test"])
    marker = b"synthetic-sensitive-package-body"

    response = client.post(
        url,
        _post_data(marker),
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.templates[0].name == "documents/_template_upload_workflow.html"
    assert "HX-Request" in response.headers["Vary"]
    template = TemplateVersion.objects.get(version="v1.0")
    assert template.status == TemplateVersion.Status.INVALID
    body = response.content.decode()
    assert marker.decode() not in body
    assert template.storage_key not in body
    assert "not_zip" not in body


@pytest.mark.parametrize(
    ("data", "expected_value"),
    [
        (_post_data(version=""), "SYNTHETIC-APPROVAL-UI-001"),
        (_post_data(approval_reference=""), "v1.0"),
    ],
)
def test_validation_failure_returns_swappable_422_with_values_and_linked_summary(
    client: Client, user_factory: object, data: dict[str, object], expected_value: str
) -> None:
    client.force_login(_actor(user_factory))
    url = reverse("documents:template-upload", args=["synthetic-platform-test"])

    response = client.post(url, data, headers={"HX-Request": "true"})
    body = response.content.decode()

    assert response.status_code == 422
    assert "HX-Request" in response.headers["Vary"]
    assert 'id="template-upload-errors"' in body
    assert 'tabindex="-1"' in body
    assert 'href="#id_' in body
    assert expected_value in body
    assert TemplateVersion.objects.count() == 0


def test_duplicate_version_returns_422_and_preserves_safe_text_values(
    client: Client, user_factory: object
) -> None:
    actor = _actor(user_factory)
    client.force_login(actor)
    url = reverse("documents:template-upload", args=["synthetic-platform-test"])
    first = client.post(url, _post_data())
    assert first.status_code == 302

    response = client.post(
        url,
        _post_data(version="v1.0", approval_reference="SYNTHETIC-APPROVAL-RETRY"),
    )

    assert response.status_code == 422
    body = response.content.decode()
    assert "v1.0" in body
    assert "SYNTHETIC-APPROVAL-RETRY" in body
    assert TemplateVersion.objects.count() == 1


def test_form_rejects_file_over_compressed_limit_before_service(
    client: Client, user_factory: object
) -> None:
    client.force_login(_actor(user_factory))
    url = reverse("documents:template-upload", args=["synthetic-platform-test"])

    response = client.post(url, _post_data(b"x" * (MAX_TEMPLATE_BYTES + 1)))

    assert response.status_code == 422
    assert TemplateVersion.objects.count() == 0


def test_unknown_type_is_generic_not_found_for_full_and_htmx(
    client: Client, user_factory: object
) -> None:
    client.force_login(_actor(user_factory))
    url = reverse("documents:template-upload", args=["synthetic-unknown"])

    for headers in ({}, {"HX-Request": "true"}):
        response = client.get(url, headers=headers)
        assert response.status_code == 404
        assert "synthetic-unknown" not in response.content.decode()


@pytest.mark.parametrize("view_name", ["template-list", "template-upload"])
def test_template_views_enforce_permission_matrix(
    client: Client, user_factory: object, view_name: str
) -> None:
    actor = _actor(user_factory)
    if view_name == "template-list":
        actor.user_permissions.remove(Permission.objects.get(codename="view_templates"))
        actor.groups.clear()
        actor.user_permissions.add(Permission.objects.get(codename="upload_templates"))
        url = reverse("documents:template-list")
    else:
        actor.user_permissions.remove(Permission.objects.get(codename="upload_templates"))
        actor.groups.clear()
        actor.user_permissions.add(Permission.objects.get(codename="view_templates"))
        url = reverse("documents:template-upload", args=["synthetic-platform-test"])
    client.force_login(actor)

    assert client.get(url).status_code == 403


@pytest.mark.parametrize("htmx", [False, True])
def test_upload_rejects_missing_csrf_for_normal_and_htmx(
    csrf_client: Client, user_factory: object, htmx: bool
) -> None:
    csrf_client.force_login(_actor(user_factory))
    url = reverse("documents:template-upload", args=["synthetic-platform-test"])
    headers = {"HX-Request": "true"} if htmx else {}

    response = csrf_client.post(url, _post_data(), headers=headers)

    assert response.status_code == 403
    assert TemplateVersion.objects.count() == 0


def test_normal_post_redirect_is_the_javascript_disabled_workflow(
    client: Client, user_factory: object
) -> None:
    client.force_login(_actor(user_factory))
    url = reverse("documents:template-upload", args=["synthetic-platform-test"])

    response = client.post(url, _post_data())

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("documents:template-list")


def test_server_error_is_generic_and_does_not_echo_exception(
    client: Client, user_factory: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.force_login(_actor(user_factory))
    url = reverse("documents:template-upload", args=["synthetic-platform-test"])
    monkeypatch.setattr(
        "apps.documents.views.upload_and_validate_template",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic private traceback")),
    )

    response = client.post(url, _post_data(), headers={"HX-Request": "true"})

    assert response.status_code == 500
    body = response.content.decode()
    assert "synthetic private traceback" not in body
    assert "storage_key" not in body


def test_expired_session_redirects_without_processing_upload(
    client: Client, user_factory: object
) -> None:
    client.force_login(_actor(user_factory))
    client.logout()
    url = reverse("documents:template-upload", args=["synthetic-platform-test"])

    response = client.post(url, _post_data(), headers={"HX-Request": "true"})

    assert response.status_code == 302
    assert response.headers["Location"].startswith(reverse("accounts:login"))
    assert TemplateVersion.objects.count() == 0
