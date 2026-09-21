from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from uuid import UUID

from django import forms
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.audit import record_identity_access_denied
from apps.accounts.policies import (
    ApplicationPermission,
    application_access_policy,
    application_permission_required,
    get_object_or_not_found,
)
from apps.cases.document_prefill import authorize_document_case, document_case_transfer
from apps.cases.models import CaseRecord
from apps.cases.policies import case_object_policy
from apps.core.correlation import get_request_correlation_id
from apps.documents.draft_services import (
    DraftAlreadyExists,
    DraftRevisionConflict,
    DraftSchemaMismatch,
    DraftValidationError,
    create_document_draft,
    get_document_draft,
    update_document_draft,
)
from apps.documents.forms import DocumentDraftControlForm, GenerationConfirmationForm
from apps.documents.generation_artifacts import (
    GenerationAttemptFailed,
    GenerationFailurePersistenceError,
    generate_artifact,
)
from apps.documents.generation_reservations import (
    GenerationReservationConflict,
    GenerationReservationUnavailable,
    issue_generation_idempotency_key,
    reserve_generation,
)
from apps.documents.models import DocumentDraft, GeneratedDocument, TemplateVersion
from apps.documents.prefill import DocumentPrefill, map_case_transfer
from apps.documents.registry import DocumentRegistration, UnknownDocumentTypeKey, document_registry
from apps.documents.selectors import (
    available_document_types,
    compatible_case_draft,
    get_active_template,
)


def _is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _vary(response: HttpResponse) -> HttpResponse:
    patch_vary_headers(response, ("HX-Request",))
    response.headers["Cache-Control"] = "no-store"
    return response


def _case(request: HttpRequest, case_id: UUID) -> CaseRecord:
    return get_object_or_not_found(
        actor=cast(User, request.user),
        permission=ApplicationPermission.VIEW_CASES,
        queryset=CaseRecord.objects.select_related("court"),
        object_policy=case_object_policy,
        pk=case_id,
    )


def _registration(type_key: str, *, require_active: bool = True) -> DocumentRegistration:
    try:
        registration = document_registry.get(type_key)
    except UnknownDocumentTypeKey as error:
        raise Http404("Requested content was not found.") from error
    if not registration.enabled or (
        require_active and get_active_template(registration.key) is None
    ):
        raise Http404("Requested content was not found.")
    return registration


@never_cache
@require_GET
@application_permission_required(ApplicationPermission.VIEW_DOCUMENT_DRAFTS)
def case_document_selector(request: HttpRequest, case_id: UUID) -> HttpResponse:
    case = _case(request, case_id)
    context = {
        "case": case,
        "available_types": available_document_types(),
        "is_htmx": _is_htmx(request),
    }
    template_name = (
        "documents/_document_selector.html"
        if _is_htmx(request)
        else "documents/document_selector.html"
    )
    return _vary(render(request, template_name, context))


def _formsets(
    registration: DocumentRegistration,
    *,
    data: Mapping[str, object] | None,
    initial_payload: Mapping[str, object],
) -> tuple[forms.BaseFormSet[forms.Form], ...]:
    result: list[forms.BaseFormSet[forms.Form]] = []
    for formset_class in registration.form_provider().formset_classes:
        prefix = formset_class.get_default_prefix()
        if data is not None:
            bound = formset_class(data=data, prefix=prefix)
        else:
            rows = initial_payload.get(prefix, [])
            bound = formset_class(
                initial=rows if isinstance(rows, (list, tuple)) else [], prefix=prefix
            )
        result.append(bound)
    return tuple(result)


def _payload(
    form: forms.Form, formsets: tuple[forms.BaseFormSet[forms.Form], ...]
) -> dict[str, object]:
    payload: dict[str, object] = dict(form.cleaned_data)
    for formset in formsets:
        prefix = formset.prefix or formset.get_default_prefix()
        payload[prefix] = [
            dict(row) for row in formset.cleaned_data if row and not row.get("DELETE")
        ]
    return payload


def _render_draft(
    request: HttpRequest,
    *,
    case: CaseRecord,
    registration: DocumentRegistration,
    form: forms.Form,
    formsets: tuple[forms.BaseFormSet[forms.Form], ...],
    control_form: DocumentDraftControlForm,
    draft: DocumentDraft | None,
    prefill: DocumentPrefill,
    generation_form: GenerationConfirmationForm | None = None,
    active_template: TemplateVersion | None = None,
    generation_unavailable: bool = False,
    conflict: bool = False,
    server_error: bool = False,
    status: int = 200,
) -> HttpResponse:
    context = {
        "case": case,
        "registration": registration,
        "form": form,
        "formsets": formsets,
        "control_form": control_form,
        "draft": draft,
        "field_rows": tuple(
            {
                "field": field,
                "provenance": prefill.sources.get(field.name),
                "override": prefill.overrides.get(field.name),
            }
            for field in form
        ),
        "conflict": conflict,
        "server_error": server_error,
        "generation_form": generation_form,
        "active_template": active_template,
        "generation_unavailable": generation_unavailable,
        "can_write": case.status == CaseRecord.Status.ACTIVE,
        "form_action": reverse("documents:case-document-draft", args=[case.pk, registration.key]),
        "selector_url": reverse("documents:case-document-selector", args=[case.pk]),
        "is_htmx": _is_htmx(request),
    }
    template_name = (
        "documents/_document_draft_form.html"
        if _is_htmx(request)
        else "documents/document_draft.html"
    )
    return _vary(render(request, template_name, context, status=status))


def _generation_form(
    *,
    actor: User,
    case: CaseRecord,
    draft: DocumentDraft | None,
    template: TemplateVersion | None,
) -> GenerationConfirmationForm | None:
    if (
        draft is None
        or draft.state != DocumentDraft.State.READY
        or case.status != CaseRecord.Status.ACTIVE
        or template is None
        or not application_access_policy.has_permission(
            actor, ApplicationPermission.GENERATE_DOCUMENTS
        )
    ):
        return None
    return GenerationConfirmationForm(
        initial={
            "intent": "generate",
            "draft_id": draft.pk,
            "expected_case_revision": case.revision,
            "expected_draft_revision": draft.revision,
            "schema_version": draft.schema_version,
            "expected_template_id": template.pk,
            "idempotency_key": issue_generation_idempotency_key(),
        }
    )


def _require_generation_permission(request: HttpRequest) -> None:
    if application_access_policy.has_permission(
        request.user, ApplicationPermission.GENERATE_DOCUMENTS
    ):
        return
    record_identity_access_denied(
        request=request,
        actor=cast(User, request.user),
        permission=ApplicationPermission.GENERATE_DOCUMENTS.value,
        correlation_id=get_request_correlation_id(request),
        route_name=request.resolver_match.view_name if request.resolver_match else "",
        is_htmx=_is_htmx(request),
    )
    raise PermissionDenied


def _render_generation_result(
    request: HttpRequest,
    *,
    case: CaseRecord,
    registration: DocumentRegistration,
    attempt: GeneratedDocument,
    status: int = 200,
) -> HttpResponse:
    context = {
        "case": case,
        "registration": registration,
        "attempt": attempt,
        "draft_url": reverse("documents:case-document-draft", args=[case.pk, registration.key]),
        "history_url": reverse("documents:case-generation-history", args=[case.pk]),
        "is_htmx": _is_htmx(request),
    }
    template_name = (
        "documents/_generation_result.html"
        if _is_htmx(request)
        else "documents/generation_result.html"
    )
    return _vary(render(request, template_name, context, status=status))


def _confirmed_generation(
    request: HttpRequest,
    *,
    case: CaseRecord,
    registration: DocumentRegistration,
    draft: DocumentDraft | None,
    prefill: DocumentPrefill,
    active_template: TemplateVersion | None,
) -> HttpResponse:
    _require_generation_permission(request)
    if case.status != CaseRecord.Status.ACTIVE:
        raise PermissionDenied
    confirmation = GenerationConfirmationForm(request.POST)
    if active_template is None:
        if draft is None:
            raise PermissionDenied
        return _render_generation_conflict(
            request,
            case=case,
            registration=registration,
            draft=draft,
            prefill=prefill,
            active_template=None,
            unavailable=True,
        )
    if not confirmation.is_valid() or draft is None:
        bundle = registration.form_provider()
        form = bundle.form_class(initial=dict(prefill.form_initial))
        formsets = _formsets(
            registration,
            data=None,
            initial_payload=prefill.formset_initial,
        )
        control = DocumentDraftControlForm(
            initial={
                "draft_id": draft.pk if draft else None,
                "revision": draft.revision if draft else None,
                "schema_version": registration.schema_version,
                "state": draft.state if draft else DocumentDraft.State.DRAFT,
            }
        )
        return _render_draft(
            request,
            case=case,
            registration=registration,
            form=form,
            formsets=formsets,
            control_form=control,
            draft=draft,
            prefill=prefill,
            generation_form=confirmation,
            active_template=active_template,
            status=422,
        )
    cleaned = confirmation.cleaned_data
    if cleaned["draft_id"] != draft.pk or cleaned["schema_version"] != registration.schema_version:
        return _render_generation_conflict(
            request,
            case=case,
            registration=registration,
            draft=draft,
            prefill=prefill,
            active_template=active_template,
        )
    try:
        attempt = reserve_generation(
            actor=cast(User, request.user),
            case_id=case.pk,
            draft_id=draft.pk,
            type_key=registration.key,
            schema_version=registration.schema_version,
            expected_case_revision=cleaned["expected_case_revision"],
            expected_draft_revision=cleaned["expected_draft_revision"],
            expected_template_id=cleaned["expected_template_id"],
            idempotency_key=cleaned["idempotency_key"],
            correlation_id=get_request_correlation_id(request),
        )
        generated = generate_artifact(
            actor=cast(User, request.user),
            attempt_id=attempt.pk,
            correlation_id=get_request_correlation_id(request),
        )
    except GenerationReservationConflict:
        return _render_generation_conflict(
            request,
            case=case,
            registration=registration,
            draft=draft,
            prefill=prefill,
            active_template=active_template,
        )
    except GenerationReservationUnavailable:
        return _render_generation_conflict(
            request,
            case=case,
            registration=registration,
            draft=draft,
            prefill=prefill,
            active_template=active_template,
            unavailable=True,
        )
    except GenerationAttemptFailed as error:
        failed = GeneratedDocument.objects.get(
            pk=error.attempt_id,
            actor=cast(User, request.user),
        )
        return _render_generation_result(
            request,
            case=case,
            registration=registration,
            attempt=failed,
        )
    except (DatabaseError, GenerationFailurePersistenceError):
        return _render_generation_conflict(
            request,
            case=case,
            registration=registration,
            draft=draft,
            prefill=prefill,
            active_template=active_template,
            unavailable=True,
            status=500,
        )
    return _render_generation_result(
        request,
        case=case,
        registration=registration,
        attempt=generated,
    )


def _render_generation_conflict(
    request: HttpRequest,
    *,
    case: CaseRecord,
    registration: DocumentRegistration,
    draft: DocumentDraft,
    prefill: DocumentPrefill,
    active_template: TemplateVersion | None,
    unavailable: bool = False,
    status: int = 409,
) -> HttpResponse:
    bundle = registration.form_provider()
    return _render_draft(
        request,
        case=case,
        registration=registration,
        form=bundle.form_class(initial=dict(prefill.form_initial)),
        formsets=_formsets(
            registration,
            data=None,
            initial_payload=prefill.formset_initial,
        ),
        control_form=DocumentDraftControlForm(
            initial={
                "draft_id": draft.pk,
                "revision": draft.revision,
                "schema_version": registration.schema_version,
                "state": draft.state,
            }
        ),
        draft=draft,
        prefill=prefill,
        active_template=active_template,
        conflict=not unavailable,
        generation_unavailable=unavailable,
        status=status,
    )


@never_cache
@require_http_methods(["GET", "POST"])
@application_permission_required(ApplicationPermission.VIEW_DOCUMENT_DRAFTS)
def case_document_draft(request: HttpRequest, case_id: UUID, type_key: str) -> HttpResponse:
    case = _case(request, case_id)
    generation_request = request.method == "POST" and request.POST.get("intent") == "generate"
    registration = _registration(type_key, require_active=not generation_request)
    found = compatible_case_draft(case_id=case.pk, registration=registration)
    if found is not None:
        found = get_document_draft(
            actor=cast(User, request.user),
            draft_id=found.pk,
            correlation_id=get_request_correlation_id(request),
        )
    bundle = registration.form_provider()
    initial_payload: Mapping[str, object] = found.payload if found else {}
    transfer = document_case_transfer(
        authorize_document_case(actor=cast(User, request.user), case_id=case.pk)
    )
    prefill = map_case_transfer(
        registration=registration,
        transfer=transfer,
        draft_payload=initial_payload,
    )
    active_template = get_active_template(registration.key)

    if request.method == "GET":
        form = bundle.form_class(initial=dict(prefill.form_initial))
        formsets = _formsets(registration, data=None, initial_payload=prefill.formset_initial)
        control = DocumentDraftControlForm(
            initial={
                "draft_id": found.pk if found else None,
                "revision": found.revision if found else None,
                "schema_version": registration.schema_version,
                "state": found.state if found else DocumentDraft.State.DRAFT,
            }
        )
        return _render_draft(
            request,
            case=case,
            registration=registration,
            form=form,
            formsets=formsets,
            control_form=control,
            draft=found,
            prefill=prefill,
            generation_form=_generation_form(
                actor=cast(User, request.user),
                case=case,
                draft=found,
                template=active_template,
            ),
            active_template=active_template,
        )

    if generation_request:
        return _confirmed_generation(
            request,
            case=case,
            registration=registration,
            draft=found,
            prefill=prefill,
            active_template=active_template,
        )

    if case.status != CaseRecord.Status.ACTIVE:
        raise PermissionDenied
    required_permission = (
        ApplicationPermission.CHANGE_DOCUMENT_DRAFTS
        if found
        else ApplicationPermission.ADD_DOCUMENT_DRAFTS
    )
    application_access_policy.require_permission(request.user, required_permission)
    form = bundle.form_class(data=request.POST)
    formsets = _formsets(registration, data=request.POST, initial_payload={})
    control = DocumentDraftControlForm(request.POST)
    submitted_prefill = map_case_transfer(
        registration=registration,
        transfer=transfer,
        draft_payload={name: request.POST.get(name, "") for name in bundle.form_class.base_fields},
    )
    valid = form.is_valid()
    formsets_valid = all(formset.is_valid() for formset in formsets)
    control_valid = control.is_valid()
    submitted_schema = request.POST.get("schema_version") or registration.schema_version
    submitted_draft_id = request.POST.get("draft_id")
    identity_conflict = (
        submitted_schema != registration.schema_version
        or (found is not None and submitted_draft_id != str(found.pk))
        or (found is None and bool(submitted_draft_id))
    )
    if identity_conflict or (found is not None and not control_valid):
        return _render_draft(
            request,
            case=case,
            registration=registration,
            form=form,
            formsets=formsets,
            control_form=control,
            draft=found,
            prefill=submitted_prefill,
            conflict=True,
            status=409,
        )
    if not (valid and formsets_valid and control_valid):
        return _render_draft(
            request,
            case=case,
            registration=registration,
            form=form,
            formsets=formsets,
            control_form=control,
            draft=found,
            prefill=submitted_prefill,
            status=422,
        )

    try:
        if found is None:
            saved = create_document_draft(
                actor=cast(User, request.user),
                case_id=case.pk,
                type_key=registration.key,
                schema_version=registration.schema_version,
                payload=_payload(form, formsets),
                state=control.cleaned_data["state"],
                correlation_id=get_request_correlation_id(request),
            )
        else:
            saved = update_document_draft(
                actor=cast(User, request.user),
                draft_id=found.pk,
                type_key=registration.key,
                schema_version=registration.schema_version,
                expected_revision=control.cleaned_data["revision"],
                payload=_payload(form, formsets),
                state=control.cleaned_data["state"],
                correlation_id=get_request_correlation_id(request),
            )
    except (DraftRevisionConflict, DraftSchemaMismatch, DraftAlreadyExists):
        return _render_draft(
            request,
            case=case,
            registration=registration,
            form=form,
            formsets=formsets,
            control_form=control,
            draft=found,
            prefill=submitted_prefill,
            conflict=True,
            status=409,
        )
    except DraftValidationError:
        form.add_error(None, gettext("The submitted document values are invalid."))
        return _render_draft(
            request,
            case=case,
            registration=registration,
            form=form,
            formsets=formsets,
            control_form=control,
            draft=found,
            prefill=submitted_prefill,
            status=422,
        )
    except DatabaseError:
        return _render_draft(
            request,
            case=case,
            registration=registration,
            form=form,
            formsets=formsets,
            control_form=control,
            draft=found,
            prefill=submitted_prefill,
            server_error=True,
            status=500,
        )

    if _is_htmx(request):
        response = HttpResponse(status=204)
        response.headers["HX-Redirect"] = reverse(
            "documents:case-document-draft", args=[case.pk, registration.key]
        )
        return _vary(response)
    messages.success(request, gettext("The document draft was saved."))
    return redirect("documents:case-document-draft", case.pk, saved.type_key)
