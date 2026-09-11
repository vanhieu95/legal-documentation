from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.template.loader import render_to_string
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.accounts.sessions import SESSION_LAST_ACTIVITY_KEY, SESSION_STARTED_AT_KEY
from apps.cases.forms import CaseRelationshipRevisionForm, participant_formset
from apps.cases.models import CaseParticipant, CaseRecord, Entity
from apps.cases.services import update_case_participants


@pytest.fixture
def administrator(user_factory: Callable[..., User]) -> User:
    user = user_factory(username="synthetic-relationship-view-admin")
    user.groups.add(Group.objects.get(name=ADMINISTRATOR_GROUP_NAME))
    return user


def edit_url(case: CaseRecord, category: str | None = None) -> str:
    name = "cases:relationship-edit" if category else "cases:relationships-edit"
    kwargs: dict[str, object] = {"case_id": case.pk}
    if category:
        kwargs["category"] = category
    return reverse(name, kwargs=kwargs)


def management(prefix: str, total: int = 1) -> dict[str, str]:
    return {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": "0",
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "category", [None, "participants", "representations", "assignments", "hearings"]
)
def test_relationship_editor_has_full_page_and_narrow_htmx_fallback(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    category: str,
) -> None:
    case = case_factory()
    client.force_login(administrator)

    full = client.get(edit_url(case, category))
    fragment = client.get(edit_url(case, category), HTTP_HX_REQUEST="true")

    assert full.status_code == 200
    assert "cases/relationships.html" in [template.name for template in full.templates]
    assert "<html" in full.content.decode()
    assert fragment.status_code == 200
    assert "cases/_relationship_form.html" in [template.name for template in fragment.templates]
    assert "<html" not in fragment.content.decode()
    assert "HX-Request" in full.headers["Vary"]
    assert "HX-Request" in fragment.headers["Vary"]
    assert 'method="post"' in full.content.decode()


@pytest.mark.django_db
def test_participant_http_update_and_validation_and_conflict_fragments(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    entity = entity_factory(legal_name="Synthetic submitted participant")
    client.force_login(administrator)
    url = edit_url(case, "participants")
    valid = {
        "expected_revision": "1",
        **management("participants"),
        "participants-0-entity": str(entity.pk),
        "participants-0-role": CaseParticipant.Role.REQUESTER,
        "participants-0-ordering": "0",
    }

    success = client.post(url, valid, HTTP_HX_REQUEST="true")
    assert success.status_code == 200
    assert "Đã cập nhật quan hệ hồ sơ." in success.content.decode()
    assert CaseParticipant.objects.filter(case=case, entity=entity).exists()

    invalid = client.post(
        url,
        {
            "expected_revision": "2",
            **management("participants"),
            "participants-0-entity": str(entity.pk),
            "participants-0-role": "invalid-role",
            "participants-0-ordering": "0",
        },
        HTTP_HX_REQUEST="true",
    )
    assert invalid.status_code == 422
    assert "invalid-role" in invalid.content.decode()
    assert "data-error-summary" in invalid.content.decode()

    stale = client.post(url, {**valid, "expected_revision": "1"}, HTTP_HX_REQUEST="true")
    assert stale.status_code == 409
    assert str(entity) in stale.content.decode()
    assert "data-conflict-summary" in stale.content.decode()
    case.refresh_from_db()
    assert case.revision == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "category", [None, "participants", "representations", "assignments", "hearings"]
)
@pytest.mark.parametrize("is_htmx", [False, True])
def test_relationship_post_requires_csrf(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    category: str | None,
    is_htmx: bool,
) -> None:
    client = Client(enforce_csrf_checks=True)
    case = case_factory()
    client.force_login(administrator)

    headers = {"HX-Request": "true"} if is_htmx else None
    response = client.post(edit_url(case, category), {}, headers=headers)

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("principal", "remove_permission", "expected"),
    [
        ("anonymous", False, 302),
        ("inactive", False, 302),
        ("outsider", False, 403),
        ("direct-permission", False, 403),
        ("administrator", True, 403),
        ("administrator", False, 200),
        ("superuser", False, 200),
    ],
)
def test_relationship_editor_authorization_matrix(
    client: Client,
    administrator: User,
    user_factory: Callable[..., User],
    case_factory: Callable[..., CaseRecord],
    principal: str,
    remove_permission: bool,
    expected: int,
) -> None:
    case = case_factory()
    user: User | None
    if principal == "anonymous":
        user = None
    elif principal == "inactive":
        user = user_factory(username="synthetic-relationship-inactive", is_active=False)
    elif principal == "outsider":
        user = user_factory(username="synthetic-relationship-outsider")
    elif principal == "direct-permission":
        user = user_factory(username="synthetic-relationship-direct")
        user.user_permissions.add(Permission.objects.get(codename="change_cases"))
    elif principal == "superuser":
        user = user_factory(
            username="synthetic-relationship-superuser", is_superuser=True, is_staff=True
        )
    else:
        user = administrator
    if remove_permission:
        Group.objects.get(name=ADMINISTRATOR_GROUP_NAME).permissions.remove(
            Permission.objects.get(codename="change_cases")
        )
    if user:
        client.force_login(user)

    assert client.get(edit_url(case, "participants")).status_code == expected


@pytest.mark.django_db
def test_expired_htmx_relationship_request_contains_no_case_data(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory(internal_reference="SYN-RELATIONSHIP-EXPIRY-SECRET")
    client.force_login(administrator)
    session = client.session
    expired = (timezone.now() - timedelta(hours=9)).timestamp()
    session[SESSION_STARTED_AT_KEY] = expired
    session[SESSION_LAST_ACTIVITY_KEY] = expired
    session.save()

    response = client.get(edit_url(case, "participants"), HTTP_HX_REQUEST="true")

    assert response.status_code == 401
    assert response.content == b""
    assert response.headers["HX-Redirect"].startswith("/session-expired/")
    assert "EXPIRY-SECRET" not in response.content.decode()


@pytest.mark.django_db
def test_normal_relationship_submission_redirects_to_canonical_section(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    entity = entity_factory()
    client.force_login(administrator)
    response = client.post(
        edit_url(case, "participants"),
        {
            "expected_revision": "1",
            **management("participants"),
            "participants-0-entity": str(entity.pk),
            "participants-0-role": CaseParticipant.Role.WITNESS,
            "participants-0-ordering": "0",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("?section=participants")


@pytest.mark.django_db
def test_archived_case_relationships_cannot_be_edited_by_view_or_service(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    CaseRecord.objects.filter(pk=case.pk).update(
        status=CaseRecord.Status.ARCHIVED,
        archived_by=administrator,
        archived_at=timezone.now(),
        archive_reason="Synthetic archive for relationship denial",
    )
    client.force_login(administrator)

    assert client.get(edit_url(case, "participants")).status_code == 403
    with pytest.raises(PermissionDenied):
        update_case_participants(
            actor=administrator,
            case_id=case.pk,
            expected_revision=case.revision,
            data={**management("participants", total=0)},
            correlation_id="synthetic-archived-denial",
        )


@pytest.mark.django_db
def test_relationship_editor_rendering_has_a_fixed_query_budget(
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    sparse_case = case_factory()
    dense_case = case_factory()
    for ordering in range(12):
        CaseParticipant.objects.create(
            case=dense_case,
            entity=entity_factory(),
            role=CaseParticipant.Role.WITNESS,
            ordering=ordering,
        )

    def render_query_count(case: CaseRecord) -> int:
        with CaptureQueriesContext(connection) as queries:
            formset = participant_formset(case=case)
            context = {
                "case": case,
                "formset_entries": (("participants", "Participants", formset),),
                "revision_form": CaseRelationshipRevisionForm(
                    initial={"expected_revision": case.revision}
                ),
                "form_action": "/synthetic/",
                "cancel_url": "/synthetic/",
                "has_relationship_errors": False,
                "success": False,
                "conflict": False,
            }
            render_to_string("cases/_relationship_form.html", context)
        return len(queries)

    sparse_queries = render_query_count(sparse_case)
    dense_queries = render_query_count(dense_case)

    assert sparse_queries <= 5
    assert dense_queries == sparse_queries
