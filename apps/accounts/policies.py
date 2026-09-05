from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from functools import wraps
from typing import Concatenate, ParamSpec, Protocol, TypeVar

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.models import Model, QuerySet
from django.http import Http404, HttpRequest, HttpResponse

from apps.accounts.audit import record_identity_access_denied
from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.core.correlation import get_request_correlation_id


class ApplicationPermission(StrEnum):
    VIEW_CASES = "accounts.view_cases"
    ADD_CASES = "accounts.add_cases"
    CHANGE_CASES = "accounts.change_cases"
    ARCHIVE_CASES = "accounts.archive_cases"
    RESTORE_CASES = "accounts.restore_cases"
    VIEW_REFERENCE_ENTITIES = "accounts.view_reference_entities"
    ADD_REFERENCE_ENTITIES = "accounts.add_reference_entities"
    CHANGE_REFERENCE_ENTITIES = "accounts.change_reference_entities"
    DEACTIVATE_REFERENCE_ENTITIES = "accounts.deactivate_reference_entities"
    VIEW_DOCUMENT_DRAFTS = "accounts.view_document_drafts"
    ADD_DOCUMENT_DRAFTS = "accounts.add_document_drafts"
    CHANGE_DOCUMENT_DRAFTS = "accounts.change_document_drafts"
    GENERATE_DOCUMENTS = "accounts.generate_documents"
    VIEW_DOCUMENT_HISTORY = "accounts.view_document_history"
    DOWNLOAD_DOCUMENTS = "accounts.download_documents"
    VIEW_TEMPLATES = "accounts.view_templates"
    UPLOAD_TEMPLATES = "accounts.upload_templates"
    VALIDATE_TEMPLATES = "accounts.validate_templates"
    ACTIVATE_TEMPLATES = "accounts.activate_templates"
    DEACTIVATE_TEMPLATES = "accounts.deactivate_templates"
    VIEW_AUDIT = "accounts.view_audit"


Principal = User | AnonymousUser


class AdministratorAccessPolicy:
    """The single deny-by-default application authorization contract."""

    def is_application_administrator(self, actor: Principal) -> bool:
        if not actor.is_authenticated or not actor.is_active:
            return False
        if actor.is_superuser:
            return True
        return actor.groups.filter(name=ADMINISTRATOR_GROUP_NAME).exists()

    def has_permission(self, actor: Principal, permission: ApplicationPermission) -> bool:
        return self.is_application_administrator(actor) and actor.has_perm(permission.value)

    def require_permission(self, actor: Principal, permission: ApplicationPermission) -> None:
        if not self.has_permission(actor, permission):
            raise PermissionDenied

    def can_administer_accounts(self, actor: Principal) -> bool:
        return bool(actor.is_authenticated and actor.is_active and actor.is_superuser)

    def require_account_administration(self, actor: Principal) -> None:
        if not self.can_administer_accounts(actor):
            raise PermissionDenied


application_access_policy = AdministratorAccessPolicy()

P = ParamSpec("P")
R = TypeVar("R")
TModel = TypeVar("TModel", bound=Model)


def application_permission_required(
    permission: ApplicationPermission,
) -> Callable[
    [Callable[Concatenate[HttpRequest, P], HttpResponse]],
    Callable[Concatenate[HttpRequest, P], HttpResponse],
]:
    """Require the central policy while preserving Django's login redirect."""

    def decorator(
        view: Callable[Concatenate[HttpRequest, P], HttpResponse],
    ) -> Callable[Concatenate[HttpRequest, P], HttpResponse]:
        @wraps(view)
        def wrapped(request: HttpRequest, *args: P.args, **kwargs: P.kwargs) -> HttpResponse:
            if not request.user.is_authenticated:
                return redirect_to_login(
                    request.get_full_path(), str(settings.LOGIN_URL), REDIRECT_FIELD_NAME
                )
            if not application_access_policy.has_permission(request.user, permission):
                record_identity_access_denied(
                    request=request,
                    actor=request.user,
                    permission=permission.value,
                    correlation_id=get_request_correlation_id(request),
                    route_name=(request.resolver_match.view_name if request.resolver_match else ""),
                    is_htmx=request.headers.get("HX-Request") == "true",
                )
                application_access_policy.require_permission(request.user, permission)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def service_permission_required(
    permission: ApplicationPermission,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Recheck authorization when a sensitive service is called directly."""

    def decorator(service: Callable[P, R]) -> Callable[P, R]:
        @wraps(service)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            actor = kwargs.get("actor")
            if not isinstance(actor, (User, AnonymousUser)):
                raise PermissionDenied
            correlation_id = kwargs.get("correlation_id")
            if not application_access_policy.has_permission(actor, permission):
                if isinstance(correlation_id, str):
                    record_identity_access_denied(
                        actor=actor if isinstance(actor, User) else None,
                        permission=permission.value,
                        correlation_id=correlation_id,
                    )
                application_access_policy.require_permission(actor, permission)
            return service(*args, **kwargs)

        return wrapped

    return decorator


class ObjectAccessPolicy(Protocol[TModel]):
    """Extension point for later tenant, assignment, or ownership scoping."""

    def scope_queryset(self, actor: User, queryset: QuerySet[TModel]) -> QuerySet[TModel]: ...


def get_object_or_not_found[TModel: Model](
    *,
    actor: User,
    permission: ApplicationPermission,
    queryset: QuerySet[TModel],
    object_policy: ObjectAccessPolicy[TModel],
    **lookup: object,
) -> TModel:
    """Return only policy-scoped objects and disclose no inaccessible existence."""
    if not application_access_policy.has_permission(actor, permission):
        raise Http404("Requested content was not found.")
    try:
        return object_policy.scope_queryset(actor, queryset).get(**lookup)
    except ObjectDoesNotExist as error:
        raise Http404("Requested content was not found.") from error
