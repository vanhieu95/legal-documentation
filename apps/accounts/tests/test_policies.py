from __future__ import annotations

from collections.abc import Callable

import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.template import Context, Template
from django.test import Client
from django.urls import path

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.accounts.policies import (
    ApplicationPermission,
    ObjectAccessPolicy,
    application_access_policy,
    application_permission_required,
    get_object_or_not_found,
    service_permission_required,
)
from apps.core.views import page_not_found, permission_denied


@application_permission_required(ApplicationPermission.VIEW_CASES)
def protected_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("protected case content")


urlpatterns = [path("protected/", protected_view)]
handler403 = permission_denied
handler404 = page_not_found


class SingleUserObjectPolicy(ObjectAccessPolicy[User]):
    def __init__(self, accessible_user: User) -> None:
        self.accessible_user = accessible_user

    def scope_queryset(self, actor: User, queryset: QuerySet[User]) -> QuerySet[User]:
        return queryset.filter(pk=self.accessible_user.pk)


@pytest.fixture
def administrator_group() -> Group:
    return Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)


@pytest.fixture
def administrator(user_factory: Callable[..., User], administrator_group: Group) -> User:
    user = user_factory(username="synthetic-administrator")
    user.groups.add(administrator_group)
    return user


@pytest.mark.django_db
def test_principal_and_permission_matrix_denies_by_default(
    user_factory: Callable[..., User],
    administrator: User,
    administrator_group: Group,
) -> None:
    inactive_user = user_factory(username="synthetic-inactive", is_active=False)
    non_administrator = user_factory(username="synthetic-non-administrator")
    administrator_without_permission = user_factory(username="synthetic-restricted-admin")
    administrator_without_permission.groups.add(administrator_group)
    administrator_without_permission.user_permissions.clear()
    administrator_group.permissions.remove(
        administrator_group.permissions.get(codename="view_cases")
    )
    active_superuser = user_factory(
        username="synthetic-superuser", is_superuser=True, is_staff=True
    )

    assert not application_access_policy.has_permission(
        AnonymousUser(), ApplicationPermission.VIEW_CASES
    )
    assert not application_access_policy.has_permission(
        inactive_user, ApplicationPermission.VIEW_CASES
    )
    assert not application_access_policy.has_permission(
        non_administrator, ApplicationPermission.VIEW_CASES
    )
    assert not application_access_policy.has_permission(
        administrator_without_permission, ApplicationPermission.VIEW_CASES
    )
    assert application_access_policy.has_permission(
        active_superuser, ApplicationPermission.VIEW_CASES
    )

    administrator_group.permissions.add(
        administrator_group.permissions.model.objects.get(
            content_type__app_label="accounts", codename="view_cases"
        )
    )
    administrator = User.objects.get(pk=administrator.pk)
    assert application_access_policy.has_permission(administrator, ApplicationPermission.VIEW_CASES)


@pytest.mark.django_db
def test_inactive_superuser_is_denied(user_factory: Callable[..., User]) -> None:
    inactive_superuser = user_factory(is_active=False, is_superuser=True, is_staff=True)

    assert not application_access_policy.has_permission(
        inactive_superuser, ApplicationPermission.VIEW_CASES
    )


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_protected_view_uses_policy_and_hidden_ui_is_not_enforcement(
    client: Client,
    user_factory: Callable[..., User],
) -> None:
    non_administrator = user_factory()
    client.force_login(non_administrator)

    rendered = Template(
        "{% load account_permissions %}"
        '{% has_application_permission "accounts.view_cases" as can_view %}'
        "{% if can_view %}hidden control{% endif %}"
    ).render(Context({"user": non_administrator}))
    response = client.get("/protected/")

    assert rendered == ""
    assert response.status_code == 403
    assert b"protected case content" not in response.content
    assert "You do not have permission to access this content." in response.content.decode()


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_protected_view_redirects_anonymous_with_local_next_and_allows_admin(
    client: Client, administrator: User
) -> None:
    anonymous_response = client.get("/protected/")
    assert anonymous_response.status_code == 302
    assert anonymous_response.headers["Location"] == "/login/?next=/protected/"

    client.force_login(administrator)
    allowed_response = client.get("/protected/")
    assert allowed_response.status_code == 200
    assert allowed_response.content == b"protected case content"


@pytest.mark.urls(__name__)
def test_generic_not_found_page_does_not_repeat_the_requested_identifier(
    client: Client,
) -> None:
    response = client.get("/protected/uuid-bi-mat-khong-ton-tai/")

    assert response.status_code == 404
    assert "Requested content was not found." in response.content.decode()
    assert "uuid-bi-mat-khong-ton-tai" not in response.content.decode()


@pytest.mark.django_db
def test_direct_service_invocation_rechecks_permission(
    user_factory: Callable[..., User], administrator: User
) -> None:
    @service_permission_required(ApplicationPermission.GENERATE_DOCUMENTS)
    def generate_document(*, actor: User | None = None) -> str:
        return "generated"

    with pytest.raises(PermissionDenied):
        generate_document(actor=user_factory())
    with pytest.raises(PermissionDenied):
        generate_document()
    assert generate_document(actor=administrator) == "generated"


@pytest.mark.django_db
def test_inaccessible_and_nonexistent_objects_have_identical_behavior(
    user_factory: Callable[..., User], administrator: User
) -> None:
    accessible_user = user_factory(username="synthetic-accessible-object")
    inaccessible_user = user_factory(username="synthetic-inaccessible-object")
    object_policy = SingleUserObjectPolicy(accessible_user)

    found = get_object_or_not_found(
        actor=administrator,
        permission=ApplicationPermission.VIEW_CASES,
        queryset=User.objects.all(),
        object_policy=object_policy,
        pk=accessible_user.pk,
    )

    assert found == accessible_user
    for identifier in (inaccessible_user.pk, 999_999):
        with pytest.raises(Http404) as error:
            get_object_or_not_found(
                actor=administrator,
                permission=ApplicationPermission.VIEW_CASES,
                queryset=User.objects.all(),
                object_policy=object_policy,
                pk=identifier,
            )
        assert str(error.value) == "Requested content was not found."


@pytest.mark.django_db
def test_uuid_knowledge_does_not_bypass_global_permission(
    user_factory: Callable[..., User],
) -> None:
    non_administrator = user_factory(username="synthetic-known-id-actor")
    known_object = user_factory(username="synthetic-known-id-object")
    object_policy = SingleUserObjectPolicy(known_object)

    with pytest.raises(Http404):
        get_object_or_not_found(
            actor=non_administrator,
            permission=ApplicationPermission.VIEW_CASES,
            queryset=User.objects.all(),
            object_policy=object_policy,
            pk=known_object.pk,
        )


@pytest.mark.django_db
def test_normal_administrator_cannot_administer_users_or_groups(
    administrator: User,
) -> None:
    assert not application_access_policy.can_administer_accounts(administrator)
    with pytest.raises(PermissionDenied):
        application_access_policy.require_account_administration(administrator)


def test_presentation_helper_denies_missing_principal_and_unknown_permission() -> None:
    missing_principal = Template(
        "{% load account_permissions %}"
        '{% has_application_permission "accounts.view_cases" as allowed %}'
        "{{ allowed }}"
    ).render(Context())
    unknown_permission = Template(
        "{% load account_permissions %}"
        '{% has_application_permission "accounts.unknown" as allowed %}'
        "{{ allowed }}"
    ).render(Context({"user": AnonymousUser()}))

    assert missing_principal == "False"
    assert unknown_permission == "False"
