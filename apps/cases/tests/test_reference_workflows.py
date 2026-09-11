from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import cast

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.audit.actions import AuditOutcome
from apps.audit.models import AuditEvent
from apps.cases.forms import CourtForm
from apps.cases.models import Court, Entity, EntityAddress, Official
from apps.cases.services import create_court, deactivate_court, update_court

PASSWORD = "synthetic-test-password"


@pytest.fixture
def administrator_group() -> Group:
    return Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)


@pytest.fixture
def administrator(user_factory: Callable[..., User], administrator_group: Group) -> User:
    user = user_factory(username="synthetic-reference-admin", password=PASSWORD)
    user.groups.add(administrator_group)
    return user


def _list_url(reference_type: str) -> str:
    return reverse("cases:reference-list", kwargs={"reference_type": reference_type})


def _create_url(reference_type: str) -> str:
    return reverse("cases:reference-create", kwargs={"reference_type": reference_type})


def _edit_url(reference_type: str, object_id: uuid.UUID) -> str:
    return reverse(
        "cases:reference-edit",
        kwargs={"reference_type": reference_type, "object_id": object_id},
    )


def _deactivate_url(reference_type: str, object_id: uuid.UUID) -> str:
    return reverse(
        "cases:reference-deactivate",
        kwargs={"reference_type": reference_type, "object_id": object_id},
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("principal", "expected_status"),
    [
        ("anonymous", 302),
        ("inactive", 302),
        ("non_administrator", 403),
        ("missing_permission", 403),
        ("administrator", 200),
        ("superuser", 200),
    ],
)
def test_reference_list_authorization_matrix(
    client: Client,
    user_factory: Callable[..., User],
    administrator_group: Group,
    administrator: User,
    principal: str,
    expected_status: int,
) -> None:
    if principal == "anonymous":
        user = None
    elif principal == "inactive":
        user = user_factory(username="synthetic-inactive-reference-user", is_active=False)
    elif principal == "non_administrator":
        user = user_factory(username="synthetic-reference-outsider")
    elif principal == "missing_permission":
        user = administrator
        permission = Permission.objects.get(codename="view_reference_entities")
        administrator_group.permissions.remove(permission)
    elif principal == "administrator":
        user = administrator
    else:
        user = user_factory(
            username="synthetic-reference-superuser", is_staff=True, is_superuser=True
        )
    if user is not None:
        client.force_login(user)

    response = client.get(_list_url("courts"))

    assert response.status_code == expected_status


@pytest.mark.django_db
def test_reference_service_rechecks_permission_and_object_policy(
    user_factory: Callable[..., User], court_factory: Callable[..., Court]
) -> None:
    outsider = user_factory(username="synthetic-service-outsider")
    court = court_factory()
    form = CourtForm(
        data={
            "code": "SYN-SERVICE",
            "full_name": "Synthetic Service Court",
            "short_name": "Service Court",
            "level": Court.Level.DISTRICT,
            "address": "Synthetic service address",
        }
    )
    assert form.is_valid()

    with pytest.raises(PermissionDenied):
        create_court(actor=outsider, form=form, correlation_id="synthetic-service-denied")
    with pytest.raises(PermissionDenied):
        update_court(
            actor=outsider,
            court_id=court.pk,
            form=form,
            correlation_id="synthetic-service-update-denied",
        )
    with pytest.raises(PermissionDenied):
        deactivate_court(
            actor=outsider,
            court_id=court.pk,
            correlation_id="synthetic-service-deactivate-denied",
        )


@pytest.mark.django_db
@pytest.mark.parametrize("reference_type", ["courts", "entities", "addresses", "officials"])
def test_reference_lists_are_full_pages_or_narrow_htmx_fragments(
    client: Client, administrator: User, reference_type: str
) -> None:
    client.force_login(administrator)

    full_response = client.get(_list_url(reference_type))
    fragment_response = client.get(_list_url(reference_type), HTTP_HX_REQUEST="true")

    assert full_response.status_code == 200
    assert "<html" in full_response.content.decode()
    assert fragment_response.status_code == 200
    assert "<html" not in fragment_response.content.decode()
    assert 'id="reference-results"' in fragment_response.content.decode()
    assert "HX-Request" in full_response.headers["Vary"]
    assert "HX-Request" in fragment_response.headers["Vary"]


@pytest.mark.django_db
def test_reference_list_supports_initial_and_filtered_empty_states(
    client: Client, administrator: User, court_factory: Callable[..., Court]
) -> None:
    client.force_login(administrator)
    initial = client.get(_list_url("courts"))
    assert "reference-empty-initial" in initial.content.decode()

    court_factory(full_name="Tòa án thử nghiệm Unicode")
    filtered = client.get(_list_url("courts"), {"q": "không tồn tại"})
    assert "reference-empty-filtered" in filtered.content.decode()


@pytest.mark.django_db
def test_valid_normal_court_create_redirects_and_audits_only_field_names(
    client: Client, administrator: User
) -> None:
    client.force_login(administrator)
    response = client.post(
        _create_url("courts"),
        {
            "code": "SYN-NEW",
            "full_name": "Tòa án nhân dân thử nghiệm",
            "short_name": "TAND thử nghiệm",
            "level": Court.Level.DISTRICT,
            "address": "Địa chỉ hành chính tổng hợp",
        },
    )

    assert response.status_code == 302
    assert "HX-Request" in response.headers["Vary"]
    court = Court.objects.get(code="SYN-NEW")
    assert response.headers["Location"] == _edit_url("courts", court.pk)
    event = AuditEvent.objects.get(action="reference.court_created")
    assert event.outcome == AuditOutcome.SUCCESS
    assert event.changed_fields == ["address", "code", "full_name", "level", "short_name"]
    assert "Tòa án" not in str(event.metadata)


@pytest.mark.django_db
def test_invalid_htmx_create_returns_swappable_422_and_preserves_unicode(
    client: Client, administrator: User
) -> None:
    client.force_login(administrator)
    response = client.post(
        _create_url("courts"),
        {
            "code": "",
            "full_name": "Tòa án thử nghiệm đã nhập",
            "short_name": "",
            "level": Court.Level.DISTRICT,
            "address": "Địa chỉ thử nghiệm",
        },
        HTTP_HX_REQUEST="true",
    )

    html = response.content.decode()
    assert response.status_code == 422
    assert 'id="reference-form"' in html
    assert "Tòa án thử nghiệm đã nhập" in html
    assert "data-error-summary" in html
    assert 'href="#id_code"' in html
    assert "<html" not in html
    assert "HX-Request" in response.headers["Vary"]
    assert AuditEvent.objects.filter(
        action="reference.court_created", outcome=AuditOutcome.FAILURE
    ).exists()


@pytest.mark.django_db
def test_htmx_edit_requeries_relation_and_rejects_inactive_superior(
    client: Client,
    administrator: User,
    court_factory: Callable[..., Court],
) -> None:
    court = court_factory(code="SYN-EDIT")
    inactive_superior = court_factory(code="SYN-INACTIVE", is_active=False)
    client.force_login(administrator)

    response = client.post(
        _edit_url("courts", court.pk),
        {
            "code": court.code,
            "full_name": court.full_name,
            "short_name": court.short_name,
            "level": court.level,
            "address": court.address,
            "superior_court": inactive_superior.pk,
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 422
    court.refresh_from_db()
    assert court.superior_court is None
    event = AuditEvent.objects.get(action="reference.court_updated")
    assert event.outcome == AuditOutcome.FAILURE
    assert event.metadata == {
        "reason_code": "validation_error",
        "reference_type": "courts",
    }


@pytest.mark.django_db
def test_generic_not_found_does_not_echo_inaccessible_uuid(
    client: Client, administrator: User
) -> None:
    object_id = uuid.uuid4()
    client.force_login(administrator)

    response = client.get(_edit_url("entities", object_id))

    assert response.status_code == 404
    assert str(object_id) not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("is_htmx", [False, True])
def test_all_unsafe_reference_routes_reject_missing_csrf(
    csrf_client: Client,
    administrator: User,
    court_factory: Callable[..., Court],
    is_htmx: bool,
) -> None:
    court = court_factory()
    csrf_client.force_login(administrator)
    headers = {"HX-Request": "true"} if is_htmx else None

    create_response = csrf_client.post(_create_url("courts"), {}, headers=headers)
    edit_response = csrf_client.post(_edit_url("courts", court.pk), {}, headers=headers)
    deactivate_response = csrf_client.post(_deactivate_url("courts", court.pk), {}, headers=headers)

    assert create_response.status_code == 403
    assert edit_response.status_code == 403
    assert deactivate_response.status_code == 403
    court.refresh_from_db()
    assert court.is_active


@pytest.mark.django_db
def test_confirmed_deactivation_is_post_only_idempotent_and_audited(
    client: Client,
    administrator: User,
    court_factory: Callable[..., Court],
) -> None:
    court = court_factory(code="SYN-DEACTIVATE")
    client.force_login(administrator)

    confirmation = client.get(_deactivate_url("courts", court.pk))
    first = client.post(_deactivate_url("courts", court.pk))
    repeated = client.post(_deactivate_url("courts", court.pk))

    assert confirmation.status_code == 200
    assert "SYN-DEACTIVATE" in confirmation.content.decode()
    assert 'name="csrfmiddlewaretoken"' in confirmation.content.decode()
    assert first.status_code == 302
    assert repeated.status_code == 302
    court.refresh_from_db()
    assert not court.is_active
    events = AuditEvent.objects.filter(action="reference.court_deactivated")
    assert events.count() == 1
    assert events.get().changed_fields == ["is_active"]


@pytest.mark.django_db
def test_deactivating_entity_also_deactivates_its_current_dependents(
    client: Client,
    administrator: User,
    entity_factory: Callable[..., Entity],
    address_factory: Callable[..., EntityAddress],
    court_factory: Callable[..., Court],
) -> None:
    entity = entity_factory()
    address = address_factory(entity=entity)
    official = Official.objects.create(
        entity=entity,
        home_court=court_factory(),
        title="Judge",
        position="Civil division",
    )
    client.force_login(administrator)

    response = client.post(_deactivate_url("entities", entity.pk))

    assert response.status_code == 302
    entity.refresh_from_db()
    address.refresh_from_db()
    official.refresh_from_db()
    assert not entity.is_active
    assert not address.is_active
    assert not official.is_active


@pytest.mark.django_db
@pytest.mark.parametrize("route", ["create", "edit", "deactivate"])
def test_reference_write_views_reject_missing_permission(
    client: Client,
    user_factory: Callable[..., User],
    court_factory: Callable[..., Court],
    route: str,
) -> None:
    outsider = user_factory(username=f"synthetic-{route}-outsider")
    court = court_factory()
    urls = {
        "create": _create_url("courts"),
        "edit": _edit_url("courts", court.pk),
        "deactivate": _deactivate_url("courts", court.pk),
    }
    client.force_login(outsider)

    response = client.get(urls[route])

    assert response.status_code == 403
    assert AuditEvent.objects.filter(
        action="identity.access_denied", outcome=AuditOutcome.DENIED
    ).exists()


@pytest.mark.django_db
def test_inactive_current_relations_remain_available_when_editing_history(
    client: Client,
    administrator: User,
    entity_factory: Callable[..., Entity],
    address_factory: Callable[..., EntityAddress],
) -> None:
    entity = entity_factory(is_active=False)
    address = address_factory(entity=entity, is_active=False)
    client.force_login(administrator)

    response = client.get(_edit_url("addresses", address.pk))

    assert response.status_code == 200
    assert f'value="{entity.pk}"' in response.content.decode()


@pytest.mark.django_db
def test_list_never_displays_identity_or_registration_values(
    client: Client,
    administrator: User,
    entity_factory: Callable[..., Entity],
) -> None:
    identity_value = "SYN-SENSITIVE-ID-001"
    entity_factory(identity_document_number=identity_value)
    client.force_login(administrator)

    response = client.get(_list_url("entities"))

    assert identity_value not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("reference_type", ["courts", "entities", "addresses", "officials"])
def test_each_reference_type_accepts_valid_htmx_creation(
    client: Client,
    administrator: User,
    reference_type: str,
    entity_factory: Callable[..., Entity],
    court_factory: Callable[..., Court],
) -> None:
    payloads = {
        "courts": {
            "code": "SYN-HTMX",
            "full_name": "Tòa án thử nghiệm HTMX",
            "short_name": "TAND HTMX",
            "level": Court.Level.DISTRICT,
            "address": "Địa chỉ thử nghiệm HTMX",
        },
        "entities": {
            "kind": Entity.Kind.INDIVIDUAL,
            "legal_name": "Nguyễn Thử Nghiệm HTMX",
            "display_name": "Nguyễn HTMX",
            "identity_document_number": "SYN-HTMX-ID",
            "registration_number": "",
            "date_of_birth": "2000-01-01",
            "organization_type": "",
        },
    }
    if reference_type in {"addresses", "officials"}:
        entity = entity_factory(identity_document_number=f"SYN-{reference_type}-ID")
        payloads["addresses"] = {
            "entity": str(entity.pk),
            "kind": EntityAddress.Kind.CURRENT,
            "full_address": "Địa chỉ thử nghiệm quan hệ",
            "province": "Thành phố thử nghiệm",
        }
        payloads["officials"] = {
            "entity": str(entity.pk),
            "home_court": str(court_factory().pk),
            "title": "Thẩm phán thử nghiệm",
            "position": "Bộ phận dân sự",
        }
    model_counts = {
        "courts": Court.objects.count(),
        "entities": Entity.objects.count(),
        "addresses": EntityAddress.objects.count(),
        "officials": Official.objects.count(),
    }
    client.force_login(administrator)

    response = client.post(
        _create_url(reference_type), payloads[reference_type], HTTP_HX_REQUEST="true"
    )

    assert response.status_code == 204
    assert response.headers["HX-Redirect"].startswith("/case-references/")
    current_counts = {
        "courts": Court.objects.count(),
        "entities": Entity.objects.count(),
        "addresses": EntityAddress.objects.count(),
        "officials": Official.objects.count(),
    }
    assert current_counts[reference_type] == model_counts[reference_type] + 1


@pytest.mark.django_db
@pytest.mark.parametrize("reference_type", ["courts", "entities", "addresses", "officials"])
def test_each_reference_type_accepts_valid_normal_edit_and_audits_fields(
    client: Client,
    administrator: User,
    reference_type: str,
    court_factory: Callable[..., Court],
    entity_factory: Callable[..., Entity],
    address_factory: Callable[..., EntityAddress],
) -> None:
    reference: Court | Entity | EntityAddress | Official
    if reference_type == "courts":
        court = court_factory(code="SYN-UPDATE")
        reference = court
        payload = {
            "code": court.code,
            "full_name": "Tòa án thử nghiệm đã cập nhật",
            "short_name": court.short_name,
            "level": court.level,
            "address": court.address,
        }
    elif reference_type == "entities":
        reference = entity_factory(identity_document_number="SYN-UPDATE-ENTITY")
        payload = {
            "kind": reference.kind,
            "legal_name": reference.legal_name,
            "display_name": "Nguyễn Đã Cập Nhật",
            "identity_document_number": reference.identity_document_number,
            "registration_number": reference.registration_number,
            "date_of_birth": "",
            "organization_type": reference.organization_type,
        }
    elif reference_type == "addresses":
        reference = address_factory()
        payload = {
            "entity": str(reference.entity_id),
            "kind": reference.kind,
            "full_address": "Địa chỉ thử nghiệm đã cập nhật",
            "province": reference.province,
            "district": reference.district,
            "ward": reference.ward,
            "valid_from": "",
            "valid_to": "",
        }
    else:
        reference = Official.objects.create(
            entity=entity_factory(identity_document_number="SYN-UPDATE-OFFICIAL"),
            home_court=court_factory(),
            title="Thẩm phán thử nghiệm",
            position="Bộ phận dân sự",
        )
        payload = {
            "entity": str(reference.entity_id),
            "home_court": str(reference.home_court_id),
            "title": "Chức danh đã cập nhật",
            "position": reference.position,
        }
    client.force_login(administrator)

    response = client.post(_edit_url(reference_type, reference.pk), payload)

    assert response.status_code == 302
    action_subject = {
        "courts": "court",
        "entities": "entity",
        "addresses": "address",
        "officials": "official",
    }[reference_type]
    event = AuditEvent.objects.get(action=f"reference.{action_subject}_updated")
    assert event.outcome == AuditOutcome.SUCCESS
    assert event.changed_fields
    assert "Tòa án" not in str(event.metadata)


@pytest.mark.django_db
@pytest.mark.parametrize("reference_type", ["courts", "entities", "addresses", "officials"])
def test_each_reference_type_supports_confirmed_deactivation(
    client: Client,
    administrator: User,
    reference_type: str,
    court_factory: Callable[..., Court],
    entity_factory: Callable[..., Entity],
    address_factory: Callable[..., EntityAddress],
) -> None:
    reference: Court | Entity | EntityAddress | Official
    if reference_type == "courts":
        reference = court_factory()
    elif reference_type == "entities":
        reference = entity_factory(identity_document_number="SYN-DEACTIVATE-ENTITY")
    elif reference_type == "addresses":
        reference = address_factory()
    else:
        reference = Official.objects.create(
            entity=entity_factory(identity_document_number="SYN-DEACTIVATE-OFFICIAL"),
            home_court=court_factory(),
            title="Thẩm phán thử nghiệm",
            position="Bộ phận dân sự",
        )
    client.force_login(administrator)

    response = client.post(_deactivate_url(reference_type, reference.pk))

    assert response.status_code == 302
    reference.refresh_from_db()
    assert not reference.is_active
    action_subject = {
        "courts": "court",
        "entities": "entity",
        "addresses": "address",
        "officials": "official",
    }[reference_type]
    event = AuditEvent.objects.get(action=f"reference.{action_subject}_deactivated")
    assert event.changed_fields == ["is_active"]


@pytest.mark.django_db
@pytest.mark.parametrize("reference_type", ["courts", "entities", "addresses", "officials"])
def test_each_reference_type_preserves_invalid_htmx_submission(
    client: Client, administrator: User, reference_type: str
) -> None:
    entered_values = {
        "courts": ("full_name", "Tòa án lỗi thử nghiệm"),
        "entities": ("legal_name", "Nguyễn Lỗi Thử Nghiệm"),
        "addresses": ("full_address", "Địa chỉ lỗi thử nghiệm"),
        "officials": ("title", "Chức danh lỗi thử nghiệm"),
    }
    field, entered_value = entered_values[reference_type]
    client.force_login(administrator)

    response = client.post(
        _create_url(reference_type), {field: entered_value}, HTTP_HX_REQUEST="true"
    )

    assert response.status_code == 422
    assert entered_value in response.content.decode()
    assert "data-error-summary" in response.content.decode()


@pytest.mark.django_db
def test_reference_list_is_bounded_paginated_and_query_efficient(
    client: Client,
    administrator: User,
    court_factory: Callable[..., Court],
    django_assert_max_num_queries: object,
) -> None:
    for _index in range(27):
        court_factory()
    client.force_login(administrator)

    query_budget = cast(
        Callable[[int], AbstractContextManager[None]], django_assert_max_num_queries
    )
    with query_budget(15):
        response = client.get(_list_url("courts"))

    assert response.status_code == 200
    assert response.content.decode().count("<tr>") == 26
    assert "page=2" in response.content.decode()


@pytest.mark.django_db
def test_reference_list_rejects_unbounded_query_without_running_selector(
    client: Client, administrator: User
) -> None:
    client.force_login(administrator)
    response = client.get(_list_url("courts"), {"q": "x" * 101})

    assert response.status_code == 200
    assert "Filter error" in response.content.decode() or "Lỗi bộ lọc" in response.content.decode()


@pytest.mark.django_db
def test_reference_list_has_a_safe_database_error_state(
    client: Client,
    administrator: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.cases import views

    def fail_list(**kwargs: object) -> object:
        raise views.DatabaseError("synthetic failure")

    monkeypatch.setattr(views, "list_references", fail_list)
    client.force_login(administrator)

    response = client.get(_list_url("courts"), HTTP_HX_REQUEST="true")

    assert response.status_code == 503
    assert "reference-results" in response.content.decode()
    assert "synthetic failure" not in response.content.decode()
