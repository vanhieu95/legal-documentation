from __future__ import annotations

from typing import Any, BinaryIO, cast

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.translation import gettext, gettext_noop
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.policies import ApplicationPermission, application_permission_required
from apps.core.correlation import get_request_correlation_id
from apps.documents.forms import TemplateUploadForm
from apps.documents.models import TemplateVersion
from apps.documents.registry import DocumentRegistration, UnknownDocumentTypeKey, document_registry
from apps.documents.services import (
    DuplicateTemplateVersion,
    InvalidTemplateUpload,
    TemplateStorageError,
    upload_and_validate_template,
)

_REPORT_LABELS = {
    "not_zip": gettext_noop("The file is not a readable DOCX package."),
    "package_invalid": gettext_noop("The DOCX package did not pass security validation."),
    "split_token": gettext_noop("A template token is split across incompatible Word runs."),
    "render_error": gettext_noop("A synthetic validation render could not be completed."),
    "unresolved_token": gettext_noop("A synthetic output contains an unresolved template token."),
    "unicode_missing": gettext_noop(
        "Expected Vietnamese Unicode text is missing from a synthetic output."
    ),
}
_DEFAULT_REPORT_LABEL = gettext_noop("The template did not pass automated validation.")


def _is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _vary(response: HttpResponse) -> HttpResponse:
    patch_vary_headers(response, ("HX-Request",))
    response.headers["Cache-Control"] = "no-store"
    return response


def _registered_type(type_key: str) -> DocumentRegistration:
    try:
        registration = document_registry.get(type_key)
    except UnknownDocumentTypeKey as error:
        raise Http404("Requested content was not found.") from error
    if not registration.enabled:
        raise Http404("Requested content was not found.")
    return registration


def _safe_report(template: TemplateVersion) -> tuple[str, ...]:
    categories = template.validation_report.get("categories", [])
    if not isinstance(categories, list):
        return (gettext("The validation report is unavailable."),)
    return tuple(
        gettext(_REPORT_LABELS.get(category, _DEFAULT_REPORT_LABEL))
        for category in categories[:10]
        if isinstance(category, str)
    )


def _template_rows(page: Any) -> list[dict[str, object]]:
    registrations = {item["key"]: item for item in document_registry.describe() if item["enabled"]}
    rows: list[dict[str, object]] = []
    for template in page.object_list:
        registration = registrations.get(template.type_key)
        if registration is None:
            continue
        rows.append(
            {
                "template": template,
                "registration": registration,
                "report_items": _safe_report(template),
                "is_candidate": template.status == TemplateVersion.Status.VALID,
            }
        )
    return rows


@never_cache
@require_GET
@application_permission_required(ApplicationPermission.VIEW_TEMPLATES)
def template_list(request: HttpRequest) -> HttpResponse:
    registered_types = tuple(item for item in document_registry.describe() if item["enabled"])
    keys = tuple(item["key"] for item in registered_types)
    versions = TemplateVersion.objects.filter(type_key__in=keys).order_by("-uploaded_at", "id")
    page = Paginator(versions, 25).get_page(request.GET.get("page"))
    context = {
        "registered_types": registered_types,
        "version_rows": _template_rows(page),
        "page": page,
        "is_htmx": _is_htmx(request),
    }
    template_name = (
        "documents/_template_list.html" if _is_htmx(request) else "documents/template_list.html"
    )
    return _vary(render(request, template_name, context))


def _upload_context(
    *,
    request: HttpRequest,
    registration: DocumentRegistration,
    form: TemplateUploadForm,
    result: TemplateVersion | None = None,
    server_error: bool = False,
) -> dict[str, object]:
    return {
        "registration": registration,
        "form": form,
        "result": result,
        "report_items": _safe_report(result) if result is not None else (),
        "server_error": server_error,
        "form_action": reverse("documents:template-upload", args=[registration.key]),
        "is_htmx": _is_htmx(request),
    }


def _render_upload(
    request: HttpRequest,
    context: dict[str, object],
    *,
    status: int = 200,
) -> HttpResponse:
    template_name = (
        "documents/_template_upload_workflow.html"
        if _is_htmx(request)
        else "documents/template_upload.html"
    )
    return _vary(render(request, template_name, context, status=status))


@never_cache
@require_http_methods(["GET", "POST"])
@application_permission_required(ApplicationPermission.VIEW_TEMPLATES)
@application_permission_required(ApplicationPermission.UPLOAD_TEMPLATES)
@application_permission_required(ApplicationPermission.VALIDATE_TEMPLATES)
def template_upload(request: HttpRequest, type_key: str) -> HttpResponse:
    registration = _registered_type(type_key)
    if request.method == "GET":
        return _render_upload(
            request,
            _upload_context(request=request, registration=registration, form=TemplateUploadForm()),
        )

    form = TemplateUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_upload(
            request,
            _upload_context(request=request, registration=registration, form=form),
            status=422,
        )
    uploaded_file = cast("UploadedFile[Any]", form.cleaned_data["template_file"])
    try:
        result = upload_and_validate_template(
            actor=cast(User, request.user),
            type_key=registration.key,
            version=form.cleaned_data["version"],
            approval_reference=form.cleaned_data["approval_reference"],
            uploaded_file=cast(BinaryIO, uploaded_file),
            original_filename=uploaded_file.name or "template.docx",
            correlation_id=get_request_correlation_id(request),
        )
    except (DuplicateTemplateVersion, InvalidTemplateUpload) as error:
        message = (
            gettext("This template version already exists.")
            if isinstance(error, DuplicateTemplateVersion)
            else gettext("The upload metadata is invalid.")
        )
        form.add_error(None, message)
        return _render_upload(
            request,
            _upload_context(request=request, registration=registration, form=form),
            status=422,
        )
    except (TemplateStorageError, OSError, RuntimeError):
        return _render_upload(
            request,
            _upload_context(
                request=request,
                registration=registration,
                form=form,
                server_error=True,
            ),
            status=500,
        )

    if _is_htmx(request):
        return _render_upload(
            request,
            _upload_context(
                request=request,
                registration=registration,
                form=TemplateUploadForm(),
                result=result,
            ),
        )
    messages.success(request, gettext("Template upload and automated validation completed."))
    return redirect("documents:template-list")
