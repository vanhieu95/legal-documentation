from __future__ import annotations

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.test import Client
from django.urls import reverse

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.models import AuditEvent
from apps.cases.forms import CaseRecordEditForm
from apps.cases.models import CaseRecord
from apps.cases.services import CaseRevisionConflict, update_case

PASSWORD = "synthetic-test-password"


@pytest.fixture
def administrator_group() -> Group:
    return seed_administrator_permissions()


@pytest.fixture
def administrator(user_factory: Callable[..., User], administrator_group: Group) -> User:
    user = user_factory(username="synthetic-case-edit-admin", password=PASSWORD)
    user.groups.add(administrator_group)
    return user


def edit_url(case: CaseRecord | uuid.UUID) -> str:
    object_id = case.pk if isinstance(case, CaseRecord) else case
    return reverse("cases:edit", kwargs={"case_id": object_id})


def edit_payload(case: CaseRecord, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "internal_reference": case.internal_reference,
        "court": str(case.court_id),
        "matter_type": case.matter_type,
        "procedural_stage": case.procedural_stage,
        "acceptance_number": case.acceptance_number,
        "acceptance_year": case.acceptance_year or "",
        "acceptance_date": case.acceptance_date.isoformat() if case.acceptance_date else "",
        "acceptance_type_code": case.acceptance_type_code,
        "expected_revision": str(case.revision),
    }
    payload.update(overrides)
    return payload


def edit_form(case: CaseRecord, **overrides: object) -> CaseRecordEditForm:
    return CaseRecordEditForm(data=edit_payload(case, **overrides), instance=case)


@pytest.mark.django_db
def test_update_service_changes_case_once_with_server_owned_metadata_and_safe_audit(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    user_factory: Callable[..., User],
) -> None:
    case = case_factory(matter_type="Synthetic original")
    original_updated_at = case.updated_at
    attacker = user_factory(username="synthetic-edit-attacker")
    form = edit_form(
        case,
        matter_type="Nội dung Unicode đã sửa",
        created_by=str(attacker.pk),
        last_edited_by=str(attacker.pk),
        updated_at="2000-01-01T00:00:00Z",
        revision="9999",
        archived_by=str(attacker.pk),
        archive_reason="untrusted",
    )
    assert form.is_valid()

    updated = update_case(
        actor=administrator,
        case_id=case.pk,
        form=form,
        correlation_id="case-update-service",
    )

    assert updated.revision == 2
    assert updated.last_edited_by == administrator
    assert updated.created_by == case.created_by
    assert updated.updated_at > original_updated_at
    assert updated.matter_type == "Nội dung Unicode đã sửa"
    assert updated.archived_by is None
    event = AuditEvent.objects.get(action="case.updated")
    assert event.target_id == str(case.pk)
    assert event.changed_fields == ["matter_type"]
    assert event.metadata == {}
    assert "Unicode" not in str(event.metadata)


@pytest.mark.django_db
def test_update_service_requires_change_permission(
    user_factory: Callable[..., User], case_factory: Callable[..., CaseRecord]
) -> None:
    outsider = user_factory(username="synthetic-edit-service-outsider")
    case = case_factory()

    with pytest.raises(PermissionDenied):
        update_case(
            actor=outsider,
            case_id=case.pk,
            form=edit_form(case),
            correlation_id="case-update-denied",
        )

    denial = AuditEvent.objects.get(action="identity.access_denied")
    assert denial.metadata == {
        "permission": "accounts.change_cases",
        "route_name": "",
        "transport": "full_page",
    }


@pytest.mark.django_db
def test_two_clients_cannot_lose_an_update_and_stale_values_are_preserved(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory(matter_type="Synthetic original")
    stale_payload = edit_payload(case, matter_type="Giá trị tab thứ hai")
    client.force_login(administrator)

    first = client.post(edit_url(case), edit_payload(case, matter_type="Giá trị tab thứ nhất"))
    second = client.post(edit_url(case), stale_payload)
    repeated = client.post(edit_url(case), stale_payload)

    assert first.status_code == 302
    assert second.status_code == 409
    assert repeated.status_code == 409
    assert "<html" in second.content.decode()
    assert "Giá trị tab thứ hai" in second.content.decode()
    assert "data-conflict-summary" in second.content.decode()
    assert 'name="expected_revision" value="1"' in second.content.decode()
    case.refresh_from_db()
    assert case.matter_type == "Giá trị tab thứ nhất"
    assert case.revision == 2
    conflicts = AuditEvent.objects.filter(
        action="case.updated", outcome="failure", metadata={"reason_code": "revision_conflict"}
    )
    assert conflicts.count() == 2
    assert all(event.target_id == str(case.pk) for event in conflicts)


@pytest.mark.django_db
def test_htmx_conflict_is_a_swappable_fragment_with_guidance_and_vary(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    stale_payload = edit_payload(case, matter_type="Giá trị HTMX đang chờ")
    client.force_login(administrator)
    client.post(edit_url(case), edit_payload(case, matter_type="Giá trị mới trong cơ sở dữ liệu"))

    response = client.post(edit_url(case), stale_payload, HTTP_HX_REQUEST="true")

    html = response.content.decode()
    assert response.status_code == 409
    assert "<html" not in html
    assert 'id="case-form"' in html
    assert "data-conflict-summary" in html
    assert "Giá trị HTMX đang chờ" in html
    assert "Tải lại" in html
    assert "HX-Request" in response.headers["Vary"]


@pytest.mark.django_db
def test_successful_edit_supports_full_page_get_and_htmx_redirect(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    client.force_login(administrator)

    full = client.get(edit_url(case))
    htmx = client.post(
        edit_url(case),
        edit_payload(case, matter_type="Yêu cầu sửa qua HTMX"),
        HTTP_HX_REQUEST="true",
    )

    assert full.status_code == 200
    assert "<html" in full.content.decode()
    assert f'value="{case.revision}"' in full.content.decode()
    assert htmx.status_code == 204
    assert htmx.headers["HX-Redirect"] == reverse("cases:detail", kwargs={"case_id": case.pk})
    assert "HX-Request" in htmx.headers["Vary"]


@pytest.mark.django_db
def test_invalid_edit_preserves_values_and_audits_validation_failure(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    client.force_login(administrator)

    response = client.post(
        edit_url(case), edit_payload(case, matter_type="Giá trị lỗi được giữ", procedural_stage="")
    )

    assert response.status_code == 200
    assert "Giá trị lỗi được giữ" in response.content.decode()
    assert "data-error-summary" in response.content.decode()
    case.refresh_from_db()
    assert case.revision == 1
    failure = AuditEvent.objects.get(action="case.updated", outcome="failure")
    assert failure.metadata == {"reason_code": "validation_error"}


@pytest.mark.django_db
def test_invalid_htmx_edit_returns_a_swappable_422_fragment(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    client.force_login(administrator)

    response = client.post(
        edit_url(case),
        edit_payload(case, matter_type="Giá trị HTMX lỗi", procedural_stage=""),
        HTTP_HX_REQUEST="true",
    )

    html = response.content.decode()
    assert response.status_code == 422
    assert "<html" not in html
    assert "data-error-summary" in html
    assert "Giá trị HTMX lỗi" in html
    assert "HX-Request" in response.headers["Vary"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("principal", "permission_codename", "expected"),
    [
        ("anonymous", None, 302),
        ("inactive", None, 302),
        ("outsider", None, 403),
        ("administrator", "change_cases", 403),
        ("administrator", None, 200),
        ("superuser", None, 200),
    ],
)
def test_case_edit_authorization_matrix(
    client: Client,
    user_factory: Callable[..., User],
    administrator_group: Group,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    principal: str,
    permission_codename: str | None,
    expected: int,
) -> None:
    case = case_factory()
    if principal == "anonymous":
        user = None
    elif principal == "inactive":
        user = user_factory(username="synthetic-inactive-case-edit", is_active=False)
    elif principal == "outsider":
        user = user_factory(username="synthetic-case-edit-outsider")
    elif principal == "superuser":
        user = user_factory(
            username="synthetic-case-edit-superuser", is_superuser=True, is_staff=True
        )
    else:
        user = administrator
    if permission_codename:
        administrator_group.permissions.remove(Permission.objects.get(codename=permission_codename))
    if user:
        client.force_login(user)

    assert client.get(edit_url(case)).status_code == expected


@pytest.mark.django_db
@pytest.mark.parametrize("is_htmx", [False, True])
def test_case_edit_rejects_missing_csrf(
    csrf_client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    is_htmx: bool,
) -> None:
    case = case_factory()
    csrf_client.force_login(administrator)
    headers = {"HX-Request": "true"} if is_htmx else None

    response = csrf_client.post(edit_url(case), edit_payload(case), headers=headers)

    assert response.status_code == 403
    case.refresh_from_db()
    assert case.revision == 1


@pytest.mark.django_db
def test_case_edit_uses_generic_not_found_for_guessed_uuid(
    client: Client, administrator: User
) -> None:
    guessed = uuid.uuid4()
    client.force_login(administrator)

    response = client.get(edit_url(guessed))

    assert response.status_code == 404
    assert str(guessed) not in response.content.decode()


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_updates_use_atomic_compare_and_swap(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL concurrency profile.")
    case = case_factory(matter_type="Synthetic concurrent original")
    barrier = Barrier(2)

    def submit(value: str) -> str:
        close_old_connections()
        actor = User.objects.get(pk=administrator.pk)
        current = CaseRecord.objects.get(pk=case.pk)
        form = edit_form(current, matter_type=value, expected_revision="1")
        assert form.is_valid()
        barrier.wait()
        try:
            update_case(
                actor=actor,
                case_id=current.pk,
                form=form,
                correlation_id=f"case-concurrent-{value[-1]}",
            )
        except CaseRevisionConflict:
            return "conflict"
        finally:
            close_old_connections()
        return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, ("Synthetic concurrent A", "Synthetic concurrent B")))

    assert sorted(outcomes) == ["conflict", "success"]
    case.refresh_from_db()
    assert case.revision == 2
    assert case.matter_type in {"Synthetic concurrent A", "Synthetic concurrent B"}
