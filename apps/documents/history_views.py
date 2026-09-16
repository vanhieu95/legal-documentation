from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.policies import (
    ApplicationPermission,
    application_access_policy,
    application_permission_required,
    get_object_or_not_found,
)
from apps.cases.models import CaseRecord
from apps.cases.policies import case_object_policy
from apps.core.correlation import get_request_correlation_id
from apps.documents.forms import GenerationRetryForm
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
from apps.documents.models import DocumentDraft, GeneratedDocument
from apps.documents.registry import UnknownDocumentTypeKey, document_registry
from apps.documents.selectors import (
    GenerationHistoryItem,
    generation_history_page,
    get_active_template,
)


@dataclass(frozen=True, slots=True)
class GenerationHistoryRow:
    item: GenerationHistoryItem
    retry_form: GenerationRetryForm | None
    download_url: str | None


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


def _render_history(
    request: HttpRequest,
    *,
    case: CaseRecord,
    status: int = 200,
    retry_error: bool = False,
    retry_attempt_id: UUID | None = None,
) -> HttpResponse:
    history = generation_history_page(
        case_id=case.pk,
        page_number=request.GET.get("page"),
    )
    can_retry = (
        case.status == CaseRecord.Status.ACTIVE
        and application_access_policy.has_permission(
            request.user, ApplicationPermission.GENERATE_DOCUMENTS
        )
    )
    rows = tuple(
        GenerationHistoryRow(
            item=item,
            download_url=(
                reverse("documents:generated-document-download", args=[item.id])
                if item.status == GeneratedDocument.Status.GENERATED
                else None
            ),
            retry_form=(
                GenerationRetryForm(
                    initial={
                        "attempt_id": item.id,
                        "idempotency_key": issue_generation_idempotency_key(),
                    }
                )
                if can_retry and item.status == GeneratedDocument.Status.FAILED
                else None
            ),
        )
        for item in history.items
    )
    context = {
        "case": case,
        "history": history,
        "history_rows": rows,
        "retry_forms": {row.item.id: row.retry_form for row in rows if row.retry_form is not None},
        "history_url": reverse("documents:case-generation-history", args=[case.pk]),
        "retry_url": reverse("documents:retry-generation", args=[case.pk]),
        "retry_error": retry_error,
        "retry_attempt_id": retry_attempt_id,
        "is_htmx": _is_htmx(request),
    }
    template_name = (
        "documents/_generation_history.html"
        if _is_htmx(request)
        else "documents/generation_history.html"
    )
    return _vary(render(request, template_name, context, status=status))


@never_cache
@require_GET
@application_permission_required(ApplicationPermission.VIEW_DOCUMENT_HISTORY)
def case_generation_history(request: HttpRequest, case_id: UUID) -> HttpResponse:
    return _render_history(request, case=_case(request, case_id))


@never_cache
@require_POST
@application_permission_required(ApplicationPermission.VIEW_DOCUMENT_HISTORY)
@application_permission_required(ApplicationPermission.GENERATE_DOCUMENTS)
def retry_generation(request: HttpRequest, case_id: UUID) -> HttpResponse:
    case = _case(request, case_id)
    if case.status != CaseRecord.Status.ACTIVE:
        raise PermissionDenied
    form = GenerationRetryForm(request.POST)
    if not form.is_valid():
        return _render_history(request, case=case, status=422, retry_error=True)
    source = GeneratedDocument.objects.filter(
        pk=form.cleaned_data["attempt_id"],
        case=case,
        status=GeneratedDocument.Status.FAILED,
    ).first()
    if source is None:
        raise Http404("Requested content was not found.")
    try:
        registration = document_registry.get(source.type_key)
    except UnknownDocumentTypeKey as error:
        raise Http404("Requested content was not found.") from error
    draft = DocumentDraft.objects.filter(
        pk=source.source_draft_id,
        case=case,
        type_key=source.type_key,
        schema_version=source.schema_version,
        state=DocumentDraft.State.READY,
    ).first()
    template = get_active_template(source.type_key)
    if not registration.enabled or draft is None or template is None:
        return _render_history(request, case=case, status=409, retry_error=True)
    try:
        reserved = reserve_generation(
            actor=cast(User, request.user),
            case_id=case.pk,
            draft_id=draft.pk,
            type_key=registration.key,
            schema_version=registration.schema_version,
            expected_case_revision=case.revision,
            expected_draft_revision=draft.revision,
            expected_template_id=template.pk,
            idempotency_key=form.cleaned_data["idempotency_key"],
            correlation_id=get_request_correlation_id(request),
        )
        result = generate_artifact(
            actor=cast(User, request.user),
            attempt_id=reserved.pk,
            correlation_id=get_request_correlation_id(request),
        )
        retry_attempt_id = result.pk
    except GenerationAttemptFailed as error:
        retry_attempt_id = error.attempt_id
    except (GenerationReservationConflict, GenerationReservationUnavailable):
        return _render_history(request, case=case, status=409, retry_error=True)
    except (DatabaseError, GenerationFailurePersistenceError):
        return _render_history(request, case=case, status=500, retry_error=True)
    return _render_history(request, case=case, retry_attempt_id=retry_attempt_id)
