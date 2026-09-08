from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from itertools import combinations

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import DjangoAssertNumQueries

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.audit.models import AuditEvent
from apps.cases.forms import CaseRecordForm
from apps.cases.models import CaseRecord, Court
from apps.cases.selectors import case_overview_queryset
from apps.cases.services import create_case

PASSWORD = "synthetic-test-password"
ACCEPTANCE_VALUES = {
    "acceptance_number": "42",
    "acceptance_year": "2026",
    "acceptance_date": "2026-09-08",
    "acceptance_type_code": "VDS",
}


@pytest.fixture
def administrator_group() -> Group:
    return Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)


@pytest.fixture
def administrator(user_factory: Callable[..., User], administrator_group: Group) -> User:
    user = user_factory(username="synthetic-case-workflow-admin", password=PASSWORD)
    user.groups.add(administrator_group)
    return user


def create_url() -> str:
    return reverse("cases:create")


def detail_url(case: CaseRecord | uuid.UUID) -> str:
    object_id = case.pk if isinstance(case, CaseRecord) else case
    return reverse("cases:detail", kwargs={"case_id": object_id})


def valid_payload(court: Court, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "internal_reference": f"SYN-WORKFLOW-{uuid.uuid4().hex[:10]}",
        "court": str(court.pk),
        "matter_type": "Synthetic civil matter",
        "procedural_stage": CaseRecord.ProceduralStage.PRE_ACCEPTANCE,
        "acceptance_number": "",
        "acceptance_year": "",
        "acceptance_date": "",
        "acceptance_type_code": "",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_create_service_creates_incomplete_case_with_server_owned_metadata(
    administrator: User,
    court_factory: Callable[..., Court],
    user_factory: Callable[..., User],
) -> None:
    court = court_factory()
    attacker = user_factory(username="synthetic-posted-actor")
    form = CaseRecordForm(
        data={
            **valid_payload(court, matter_type="Yêu cầu dân sự thử nghiệm"),
            "created_by": str(attacker.pk),
            "last_edited_by": str(attacker.pk),
            "revision": "999",
            "created_at": "2000-01-01T00:00:00Z",
        }
    )
    assert form.is_valid()

    record = create_case(actor=administrator, form=form, correlation_id="case-create-service")

    assert record.revision == 1
    assert record.created_by == administrator
    assert record.last_edited_by == administrator
    assert record.created_at is not None
    assert record.updated_at is not None
    assert record.created_at.year != 2000
    assert record.matter_type == "Yêu cầu dân sự thử nghiệm"


@pytest.mark.django_db
def test_create_service_requires_case_add_permission(
    user_factory: Callable[..., User], court_factory: Callable[..., Court]
) -> None:
    outsider = user_factory(username="synthetic-case-service-outsider")
    form = CaseRecordForm(data=valid_payload(court_factory()))
    assert form.is_valid()

    with pytest.raises(PermissionDenied):
        create_case(actor=outsider, form=form, correlation_id="case-create-denied")


@pytest.mark.django_db
def test_normal_case_creation_redirects_to_canonical_detail_and_audits_safely(
    client: Client, administrator: User, court_factory: Callable[..., Court]
) -> None:
    court = court_factory()
    client.force_login(administrator)
    payload = valid_payload(court, matter_type="Yêu cầu giữ nguyên Unicode")

    response = client.post(create_url(), payload)

    assert response.status_code == 302
    record = CaseRecord.objects.get(internal_reference=payload["internal_reference"])
    assert response.headers["Location"] == detail_url(record)
    assert "HX-Request" in response.headers["Vary"]
    event = AuditEvent.objects.get(action="case.created")
    assert event.target_id == str(record.pk)
    assert event.changed_fields == []
    assert event.metadata == {}
    assert "Unicode" not in str(event.metadata)


@pytest.mark.django_db
def test_accepted_case_creation_requires_and_preserves_complete_acceptance_group(
    client: Client, administrator: User, court_factory: Callable[..., Court]
) -> None:
    court = court_factory()
    client.force_login(administrator)
    payload = valid_payload(
        court,
        procedural_stage=CaseRecord.ProceduralStage.ACCEPTED,
        **ACCEPTANCE_VALUES,
    )

    response = client.post(create_url(), payload)

    assert response.status_code == 302
    record = CaseRecord.objects.get(internal_reference=payload["internal_reference"])
    assert record.acceptance_date == date(2026, 9, 8)
    assert record.acceptance_year == 2026


@pytest.mark.django_db
@pytest.mark.parametrize(
    "partial_values",
    [
        dict(items)
        for size in range(1, len(ACCEPTANCE_VALUES))
        for items in combinations(ACCEPTANCE_VALUES.items(), size)
    ],
)
def test_every_partial_acceptance_group_returns_linked_errors_and_preserves_input(
    client: Client,
    administrator: User,
    court_factory: Callable[..., Court],
    partial_values: dict[str, str],
) -> None:
    court = court_factory()
    client.force_login(administrator)
    payload = valid_payload(
        court,
        matter_type="Giá trị Unicode được giữ lại",
        procedural_stage=CaseRecord.ProceduralStage.ACCEPTED,
        **partial_values,
    )

    response = client.post(create_url(), payload, HTTP_HX_REQUEST="true")

    html = response.content.decode()
    assert response.status_code == 422
    assert "<html" not in html
    assert 'id="case-form"' in html
    assert "Giá trị Unicode được giữ lại" in html
    assert "data-error-summary" in html
    assert 'href="#id_' in html
    assert "HX-Request" in response.headers["Vary"]
    event = AuditEvent.objects.get(action="case.created")
    assert event.metadata == {"reason_code": "validation_error"}
    assert "Unicode" not in str(event.metadata)


@pytest.mark.django_db
def test_create_form_only_offers_active_courts_and_rejects_inactive_post(
    client: Client,
    administrator: User,
    court_factory: Callable[..., Court],
) -> None:
    active = court_factory(code="SYN-ACTIVE-COURT")
    inactive = court_factory(code="SYN-INACTIVE-COURT", is_active=False)
    client.force_login(administrator)

    page = client.get(create_url())
    rejected = client.post(create_url(), valid_payload(inactive), HTTP_HX_REQUEST="true")

    html = page.content.decode()
    assert str(active.pk) in html
    assert str(inactive.pk) not in html
    assert rejected.status_code == 422
    assert not CaseRecord.objects.filter(court=inactive).exists()


@pytest.mark.django_db
def test_create_supports_full_and_htmx_success_responses(
    client: Client, administrator: User, court_factory: Callable[..., Court]
) -> None:
    court = court_factory()
    client.force_login(administrator)

    full = client.get(create_url())
    htmx = client.post(create_url(), valid_payload(court), HTTP_HX_REQUEST="true")

    assert full.status_code == 200
    assert "<html" in full.content.decode()
    assert "HX-Request" in full.headers["Vary"]
    assert htmx.status_code == 204
    assert htmx.headers["HX-Redirect"].startswith("/cases/")
    assert "HX-Request" in htmx.headers["Vary"]


@pytest.mark.django_db
def test_normal_invalid_case_creation_returns_full_page_and_preserves_values(
    client: Client, administrator: User, court_factory: Callable[..., Court]
) -> None:
    court = court_factory()
    client.force_login(administrator)

    response = client.post(
        create_url(),
        valid_payload(court, matter_type="Giá trị lỗi Unicode", procedural_stage=""),
    )

    html = response.content.decode()
    assert response.status_code == 200
    assert "<html" in html
    assert "Giá trị lỗi Unicode" in html
    assert "data-error-summary" in html
    assert 'href="#id_procedural_stage"' in html
    assert "HX-Request" in response.headers["Vary"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("principal", "permission_codename", "expected"),
    [
        ("anonymous", None, 302),
        ("inactive", None, 302),
        ("outsider", None, 403),
        ("administrator", "add_cases", 403),
        ("administrator", None, 200),
        ("superuser", None, 200),
    ],
)
def test_case_create_authorization_matrix(
    client: Client,
    user_factory: Callable[..., User],
    administrator_group: Group,
    administrator: User,
    principal: str,
    permission_codename: str | None,
    expected: int,
) -> None:
    user: User | None
    if principal == "anonymous":
        user = None
    elif principal == "inactive":
        user = user_factory(username="synthetic-inactive-case", is_active=False)
    elif principal == "outsider":
        user = user_factory(username="synthetic-case-outsider")
    elif principal == "superuser":
        user = user_factory(username="synthetic-case-superuser", is_superuser=True, is_staff=True)
    else:
        user = administrator
    if permission_codename:
        administrator_group.permissions.remove(Permission.objects.get(codename=permission_codename))
    if user:
        client.force_login(user)

    assert client.get(create_url()).status_code == expected


@pytest.mark.django_db
def test_case_detail_is_permission_scoped_and_summarizes_without_editing_relationships(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    record = case_factory(matter_type="Nội dung tổng quan Unicode")
    client.force_login(administrator)

    response = client.get(detail_url(record))

    html = response.content.decode()
    assert response.status_code == 200
    assert "Nội dung tổng quan Unicode" in html
    assert "data-case-overview" in html
    assert 'name="participants-TOTAL_FORMS"' not in html
    assert "HX-Request" in response.headers["Vary"]
    guessed = uuid.uuid4()
    missing = client.get(detail_url(guessed))
    assert missing.status_code == 404
    assert str(guessed) not in missing.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("principal", "permission_codename", "expected"),
    [
        ("anonymous", None, 302),
        ("inactive", None, 302),
        ("outsider", None, 403),
        ("administrator", "view_cases", 403),
        ("administrator", None, 200),
        ("superuser", None, 200),
    ],
)
def test_case_detail_authorization_matrix(
    client: Client,
    user_factory: Callable[..., User],
    administrator_group: Group,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    principal: str,
    permission_codename: str | None,
    expected: int,
) -> None:
    record = case_factory()
    if principal == "anonymous":
        user = None
    elif principal == "inactive":
        user = user_factory(username="synthetic-inactive-case-detail", is_active=False)
    elif principal == "outsider":
        user = user_factory(username="synthetic-case-detail-outsider")
    elif principal == "superuser":
        user = user_factory(
            username="synthetic-case-detail-superuser", is_superuser=True, is_staff=True
        )
    else:
        user = administrator
    if permission_codename:
        administrator_group.permissions.remove(Permission.objects.get(codename=permission_codename))
    if user:
        client.force_login(user)

    assert client.get(detail_url(record)).status_code == expected


@pytest.mark.django_db
def test_case_overview_selector_has_a_fixed_related_query_count(
    django_assert_num_queries: DjangoAssertNumQueries,
    case_factory: Callable[..., CaseRecord],
) -> None:
    record = case_factory()

    with django_assert_num_queries(5):
        selected = case_overview_queryset().get(pk=record.pk)
        list(selected.participants.all())
        list(selected.representations.all())
        list(selected.official_assignments.all())
        list(selected.hearings.all())


@pytest.mark.django_db
@pytest.mark.parametrize("is_htmx", [False, True])
def test_case_create_rejects_missing_csrf(
    csrf_client: Client,
    administrator: User,
    court_factory: Callable[..., Court],
    is_htmx: bool,
) -> None:
    csrf_client.force_login(administrator)
    headers = {"HX-Request": "true"} if is_htmx else None

    response = csrf_client.post(create_url(), valid_payload(court_factory()), headers=headers)

    assert response.status_code == 403
    assert CaseRecord.objects.count() == 0
