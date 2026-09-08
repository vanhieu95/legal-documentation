from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from django import forms
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, models
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.policies import (
    ApplicationPermission,
    application_access_policy,
    application_permission_required,
    get_object_or_not_found,
)
from apps.audit.actions import AuditAction
from apps.cases.audit import record_case_failure, record_reference_validation_failure
from apps.cases.forms import (
    CaseArchiveForm,
    CaseRecordEditForm,
    CaseRecordForm,
    CaseRestoreForm,
    CourtForm,
    EntityAddressForm,
    EntityForm,
    OfficialForm,
    ReferenceListFilterForm,
)
from apps.cases.models import CaseRecord, Court, Entity, EntityAddress, Official
from apps.cases.policies import ReferenceObjectPolicy, can_edit_case, case_object_policy
from apps.cases.selectors import (
    ReferenceListPage,
    ReferenceType,
    case_overview_queryset,
    list_references,
)
from apps.cases.services import (
    CaseRevisionConflict,
    archive_case,
    create_address,
    create_case,
    create_court,
    create_entity,
    create_official,
    deactivate_address,
    deactivate_court,
    deactivate_entity,
    deactivate_official,
    restore_case,
    update_address,
    update_case,
    update_court,
    update_entity,
    update_official,
)
from apps.core.correlation import get_request_correlation_id


@dataclass(frozen=True, slots=True)
class ReferenceConfig:
    key: ReferenceType
    singular_label: object
    plural_label: object
    model: type[models.Model]
    form_class: type[forms.ModelForm[Any]]
    create_action: AuditAction
    update_action: AuditAction
    create_service: Callable[..., models.Model]
    update_service: Callable[..., models.Model]
    deactivate_service: Callable[..., models.Model]
    id_argument: str


REFERENCE_CONFIGS = {
    "courts": ReferenceConfig(
        "courts",
        _("Court"),
        _("Courts"),
        Court,
        CourtForm,
        AuditAction.REFERENCE_COURT_CREATED,
        AuditAction.REFERENCE_COURT_UPDATED,
        create_court,
        update_court,
        deactivate_court,
        "court_id",
    ),
    "entities": ReferenceConfig(
        "entities",
        _("Entity"),
        _("Entities"),
        Entity,
        EntityForm,
        AuditAction.REFERENCE_ENTITY_CREATED,
        AuditAction.REFERENCE_ENTITY_UPDATED,
        create_entity,
        update_entity,
        deactivate_entity,
        "entity_id",
    ),
    "addresses": ReferenceConfig(
        "addresses",
        _("Address"),
        _("Addresses"),
        EntityAddress,
        EntityAddressForm,
        AuditAction.REFERENCE_ADDRESS_CREATED,
        AuditAction.REFERENCE_ADDRESS_UPDATED,
        create_address,
        update_address,
        deactivate_address,
        "address_id",
    ),
    "officials": ReferenceConfig(
        "officials",
        _("Official"),
        _("Officials"),
        Official,
        OfficialForm,
        AuditAction.REFERENCE_OFFICIAL_CREATED,
        AuditAction.REFERENCE_OFFICIAL_UPDATED,
        create_official,
        update_official,
        deactivate_official,
        "official_id",
    ),
}


def _config(reference_type: str) -> ReferenceConfig:
    try:
        return REFERENCE_CONFIGS[reference_type]
    except KeyError as error:
        raise Http404("Requested content was not found.") from error


def _is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _vary(response: HttpResponse) -> HttpResponse:
    patch_vary_headers(response, ("HX-Request",))
    return response


def _user(request: HttpRequest) -> User:
    return cast(User, request.user)


def _case_object(
    request: HttpRequest, case_id: uuid.UUID, permission: ApplicationPermission
) -> CaseRecord:
    return get_object_or_not_found(
        actor=_user(request),
        permission=permission,
        queryset=case_overview_queryset(),
        object_policy=case_object_policy,
        pk=case_id,
    )


def _render_case_form(
    request: HttpRequest,
    *,
    form: CaseRecordForm,
    case: CaseRecord | None = None,
    conflict: bool = False,
    status: int = 200,
) -> HttpResponse:
    if case is None:
        page_title = gettext("Create case")
        form_action = reverse("cases:create")
        cancel_url = reverse("cases:list")
        submit_label = gettext("Create case")
    else:
        page_title = gettext("Edit case")
        form_action = reverse("cases:edit", kwargs={"case_id": case.pk})
        cancel_url = reverse("cases:detail", kwargs={"case_id": case.pk})
        submit_label = gettext("Save case")
    context = {
        "form": form,
        "case": case,
        "conflict": conflict,
        "is_htmx": _is_htmx(request),
        "page_title": page_title,
        "form_action": form_action,
        "cancel_url": cancel_url,
        "submit_label": submit_label,
    }
    template = "cases/_case_form.html" if _is_htmx(request) else "cases/form.html"
    return _vary(render(request, template, context, status=status))


def _reference_capabilities(actor: User) -> dict[str, bool]:
    """Evaluate Administrator membership once for reference-list controls."""
    is_administrator = application_access_policy.is_application_administrator(actor)
    return {
        "can_add": is_administrator
        and actor.has_perm(ApplicationPermission.ADD_REFERENCE_ENTITIES.value),
        "can_change": is_administrator
        and actor.has_perm(ApplicationPermission.CHANGE_REFERENCE_ENTITIES.value),
        "can_deactivate": is_administrator
        and actor.has_perm(ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES.value),
    }


def _reference_label(reference: models.Model) -> str:
    if isinstance(reference, Court):
        return f"{reference.code} — {reference.short_name}"
    if isinstance(reference, Entity):
        return reference.legal_name
    if isinstance(reference, EntityAddress):
        return gettext("%(kind)s for %(entity)s") % {
            "kind": reference.get_kind_display(),
            "entity": reference.entity.legal_name,
        }
    if isinstance(reference, Official):
        return f"{reference.entity.legal_name} — {reference.title}"
    return gettext("Reference record")


def _reference_object(
    request: HttpRequest,
    config: ReferenceConfig,
    object_id: uuid.UUID,
    permission: ApplicationPermission,
) -> models.Model:
    return get_object_or_not_found(
        actor=_user(request),
        permission=permission,
        queryset=config.model._default_manager.all(),
        object_policy=ReferenceObjectPolicy[models.Model](),
        pk=object_id,
    )


def _render_form(
    request: HttpRequest,
    *,
    config: ReferenceConfig,
    form: forms.ModelForm[Any],
    mode: str,
    status: int = 200,
) -> HttpResponse:
    title_template = gettext("Create %(type)s") if mode == "create" else gettext("Edit %(type)s")
    context = {
        "config": config,
        "reference_configs": REFERENCE_CONFIGS,
        "form": form,
        "mode": mode,
        "is_htmx": _is_htmx(request),
        "page_title": title_template % {"type": config.singular_label},
        "form_action": request.path,
        "cancel_url": reverse("cases:reference-list", kwargs={"reference_type": config.key}),
    }
    template = (
        "cases/references/_reference_form.html"
        if _is_htmx(request)
        else "cases/references/form.html"
    )
    return _vary(render(request, template, context, status=status))


@never_cache
@require_GET
@application_permission_required(ApplicationPermission.VIEW_CASES)
def case_list_placeholder(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "placeholders/domain.html",
        {
            "page_title": gettext("Cases"),
            "state_message": gettext("Case management is not available yet."),
        },
    )


@never_cache
@require_http_methods(["GET", "POST"])
@application_permission_required(ApplicationPermission.ADD_CASES)
def case_create(request: HttpRequest) -> HttpResponse:
    form = CaseRecordForm(request.POST or None)
    if request.method == "POST":
        correlation_id = get_request_correlation_id(request)
        if form.is_valid():
            case = create_case(actor=_user(request), form=form, correlation_id=correlation_id)
            messages.success(request, gettext("Case created."))
            destination = reverse("cases:detail", kwargs={"case_id": case.pk})
            if _is_htmx(request):
                return _vary(HttpResponse(status=204, headers={"HX-Redirect": destination}))
            return _vary(redirect(destination))
        record_case_failure(
            actor=_user(request),
            action=AuditAction.CASE_CREATED,
            correlation_id=correlation_id,
            reason_code="validation_error",
        )
        return _render_case_form(request, form=form, status=422 if _is_htmx(request) else 200)
    return _render_case_form(request, form=form)


@never_cache
@require_GET
@application_permission_required(ApplicationPermission.VIEW_CASES)
def case_detail(request: HttpRequest, case_id: uuid.UUID) -> HttpResponse:
    case = _case_object(request, case_id, ApplicationPermission.VIEW_CASES)
    return _vary(
        render(
            request,
            "cases/detail.html",
            {
                "case": case,
                "page_title": gettext("Case overview"),
                "can_edit": can_edit_case(case)
                and application_access_policy.has_permission(
                    _user(request), ApplicationPermission.CHANGE_CASES
                ),
                "can_archive": can_edit_case(case)
                and application_access_policy.has_permission(
                    _user(request), ApplicationPermission.ARCHIVE_CASES
                ),
                "can_restore": not can_edit_case(case)
                and application_access_policy.has_permission(
                    _user(request), ApplicationPermission.RESTORE_CASES
                ),
            },
        )
    )


@never_cache
@require_http_methods(["GET", "POST"])
@application_permission_required(ApplicationPermission.CHANGE_CASES)
def case_edit(request: HttpRequest, case_id: uuid.UUID) -> HttpResponse:
    case = _case_object(request, case_id, ApplicationPermission.CHANGE_CASES)
    if not can_edit_case(case):
        raise PermissionDenied
    form = CaseRecordEditForm(request.POST or None, instance=case)
    if request.method == "POST":
        correlation_id = get_request_correlation_id(request)
        if form.is_valid():
            try:
                update_case(
                    actor=_user(request),
                    case_id=case.pk,
                    form=form,
                    correlation_id=correlation_id,
                )
            except CaseRevisionConflict:
                return _render_case_form(
                    request,
                    form=form,
                    case=case,
                    conflict=True,
                    status=409,
                )
            messages.success(request, gettext("Case updated."))
            destination = reverse("cases:detail", kwargs={"case_id": case.pk})
            if _is_htmx(request):
                return _vary(HttpResponse(status=204, headers={"HX-Redirect": destination}))
            return _vary(redirect(destination))
        record_case_failure(
            actor=_user(request),
            action=AuditAction.CASE_UPDATED,
            target_id=str(case.pk),
            correlation_id=correlation_id,
            reason_code="validation_error",
        )
        return _render_case_form(
            request,
            form=form,
            case=case,
            status=422 if _is_htmx(request) else 200,
        )
    return _render_case_form(request, form=form, case=case)


def _render_case_transition(
    request: HttpRequest,
    *,
    case: CaseRecord,
    form: CaseArchiveForm | CaseRestoreForm,
    operation: str,
    conflict: bool = False,
    status: int = 200,
) -> HttpResponse:
    is_archive = operation == "archive"
    context = {
        "case": case,
        "form": form,
        "operation": operation,
        "conflict": conflict,
        "is_htmx": _is_htmx(request),
        "page_title": gettext("Archive case") if is_archive else gettext("Restore case"),
        "submit_label": gettext("Confirm archive") if is_archive else gettext("Confirm restore"),
        "busy_label": gettext("Archiving…") if is_archive else gettext("Restoring…"),
        "form_action": reverse(f"cases:{operation}", kwargs={"case_id": case.pk}),
        "cancel_url": reverse("cases:detail", kwargs={"case_id": case.pk}),
    }
    template = "cases/_case_transition_form.html" if _is_htmx(request) else "cases/transition.html"
    return _vary(render(request, template, context, status=status))


def _case_transition(
    request: HttpRequest,
    *,
    case_id: uuid.UUID,
    operation: str,
    permission: ApplicationPermission,
) -> HttpResponse:
    case = _case_object(request, case_id, permission)
    is_archive = operation == "archive"
    form_class = CaseArchiveForm if is_archive else CaseRestoreForm
    form = form_class(request.POST or None, initial={"expected_revision": case.revision})
    if request.method == "POST":
        correlation_id = get_request_correlation_id(request)
        action = AuditAction.CASE_ARCHIVED if is_archive else AuditAction.CASE_RESTORED
        if form.is_valid():
            try:
                if isinstance(form, CaseArchiveForm):
                    archive_case(
                        actor=_user(request),
                        case_id=case.pk,
                        form=form,
                        correlation_id=correlation_id,
                    )
                else:
                    restore_case(
                        actor=_user(request),
                        case_id=case.pk,
                        form=form,
                        correlation_id=correlation_id,
                    )
            except CaseRevisionConflict:
                return _render_case_transition(
                    request,
                    case=case,
                    form=form,
                    operation=operation,
                    conflict=True,
                    status=409,
                )
            messages.success(
                request, gettext("Case archived.") if is_archive else gettext("Case restored.")
            )
            destination = reverse("cases:detail", kwargs={"case_id": case.pk})
            if _is_htmx(request):
                return _vary(HttpResponse(status=204, headers={"HX-Redirect": destination}))
            return _vary(redirect(destination))
        record_case_failure(
            actor=_user(request),
            action=action,
            target_id=str(case.pk),
            correlation_id=correlation_id,
            reason_code="validation_error",
            reason_supplied=bool(request.POST.get("reason", "").strip()) if is_archive else None,
        )
        return _render_case_transition(
            request,
            case=case,
            form=form,
            operation=operation,
            status=422 if _is_htmx(request) else 200,
        )
    return _render_case_transition(request, case=case, form=form, operation=operation)


@never_cache
@require_http_methods(["GET", "POST"])
@application_permission_required(ApplicationPermission.ARCHIVE_CASES)
def case_archive(request: HttpRequest, case_id: uuid.UUID) -> HttpResponse:
    return _case_transition(
        request,
        case_id=case_id,
        operation="archive",
        permission=ApplicationPermission.ARCHIVE_CASES,
    )


@never_cache
@require_http_methods(["GET", "POST"])
@application_permission_required(ApplicationPermission.RESTORE_CASES)
def case_restore(request: HttpRequest, case_id: uuid.UUID) -> HttpResponse:
    return _case_transition(
        request,
        case_id=case_id,
        operation="restore",
        permission=ApplicationPermission.RESTORE_CASES,
    )


@never_cache
@require_GET
@application_permission_required(ApplicationPermission.VIEW_REFERENCE_ENTITIES)
def reference_list(request: HttpRequest, reference_type: str) -> HttpResponse:
    config = _config(reference_type)
    form = ReferenceListFilterForm(request.GET)
    validation_errors: list[str] = []
    page = ReferenceListPage((), 1, 0, 0, False, False)
    unavailable = False
    if form.is_valid():
        try:
            page = list_references(
                reference_type=config.key,
                query=form.cleaned_data["q"],
                state=form.cleaned_data["state"],
                page=form.cleaned_data["page"],
            )
        except DatabaseError:
            unavailable = True
    else:
        validation_errors = [str(error) for errors in form.errors.values() for error in errors]
    context = {
        "config": config,
        "reference_configs": REFERENCE_CONFIGS,
        "form": form,
        "reference_page": page,
        "validation_errors": validation_errors,
        "unavailable": unavailable,
        "has_active_filters": bool(
            request.GET.get("q") or request.GET.get("state") not in {None, "active"}
        ),
        **_reference_capabilities(_user(request)),
    }
    template = (
        "cases/references/_reference_results.html"
        if _is_htmx(request)
        else "cases/references/list.html"
    )
    return _vary(render(request, template, context, status=503 if unavailable else 200))


@never_cache
@require_http_methods(["GET", "POST"])
@application_permission_required(ApplicationPermission.ADD_REFERENCE_ENTITIES)
def reference_create(request: HttpRequest, reference_type: str) -> HttpResponse:
    config = _config(reference_type)
    form = config.form_class(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            created = config.create_service(
                actor=_user(request),
                form=form,
                correlation_id=get_request_correlation_id(request),
            )
            messages.success(request, gettext("Reference record created."))
            destination = reverse(
                "cases:reference-edit",
                kwargs={"reference_type": config.key, "object_id": created.pk},
            )
            if _is_htmx(request):
                return _vary(HttpResponse(status=204, headers={"HX-Redirect": destination}))
            return _vary(redirect(destination))
        record_reference_validation_failure(
            actor=_user(request),
            action=config.create_action,
            reference_type=config.key,
            correlation_id=get_request_correlation_id(request),
        )
        return _render_form(
            request,
            config=config,
            form=form,
            mode="create",
            status=422 if _is_htmx(request) else 200,
        )
    return _render_form(request, config=config, form=form, mode="create")


@never_cache
@require_http_methods(["GET", "POST"])
@application_permission_required(ApplicationPermission.CHANGE_REFERENCE_ENTITIES)
def reference_edit(request: HttpRequest, reference_type: str, object_id: uuid.UUID) -> HttpResponse:
    config = _config(reference_type)
    reference = _reference_object(
        request, config, object_id, ApplicationPermission.CHANGE_REFERENCE_ENTITIES
    )
    form = config.form_class(request.POST or None, instance=reference)
    if request.method == "POST":
        if form.is_valid():
            updated = config.update_service(
                actor=_user(request),
                form=form,
                correlation_id=get_request_correlation_id(request),
                **{config.id_argument: reference.pk},
            )
            messages.success(request, gettext("Reference record updated."))
            destination = reverse(
                "cases:reference-edit",
                kwargs={"reference_type": config.key, "object_id": updated.pk},
            )
            if _is_htmx(request):
                return _vary(HttpResponse(status=204, headers={"HX-Redirect": destination}))
            return _vary(redirect(destination))
        record_reference_validation_failure(
            actor=_user(request),
            action=config.update_action,
            reference_type=config.key,
            correlation_id=get_request_correlation_id(request),
        )
        return _render_form(
            request,
            config=config,
            form=form,
            mode="edit",
            status=422 if _is_htmx(request) else 200,
        )
    return _render_form(request, config=config, form=form, mode="edit")


@never_cache
@require_http_methods(["GET", "POST"])
@application_permission_required(ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES)
def reference_deactivate(
    request: HttpRequest, reference_type: str, object_id: uuid.UUID
) -> HttpResponse:
    config = _config(reference_type)
    reference = _reference_object(
        request, config, object_id, ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES
    )
    destination = reverse("cases:reference-list", kwargs={"reference_type": config.key})
    if request.method == "POST":
        config.deactivate_service(
            actor=_user(request),
            correlation_id=get_request_correlation_id(request),
            **{config.id_argument: reference.pk},
        )
        messages.success(request, gettext("Reference record deactivated."))
        if _is_htmx(request):
            return _vary(HttpResponse(status=204, headers={"HX-Redirect": destination}))
        return _vary(redirect(destination))
    context = {
        "config": config,
        "reference": reference,
        "reference_label": _reference_label(reference),
        "page_title": gettext("Deactivate %(type)s") % {"type": config.singular_label},
        "form_action": request.path,
        "cancel_url": destination,
    }
    template = (
        "cases/references/_deactivate_form.html"
        if _is_htmx(request)
        else "cases/references/deactivate.html"
    )
    return _vary(render(request, template, context))
