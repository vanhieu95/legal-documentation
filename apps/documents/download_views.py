from __future__ import annotations

from uuid import UUID

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login
from django.http import FileResponse, Http404, HttpRequest
from django.http.response import HttpResponseBase
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.core.correlation import get_request_correlation_id
from apps.documents.downloads import (
    DOCX_CONTENT_TYPE,
    GeneratedDocumentDownloadNotFound,
    GeneratedDocumentDownloadUnavailable,
    build_content_disposition,
    open_generated_document_download,
    record_anonymous_download_denial,
)


@never_cache
@require_GET
def generated_document_download(request: HttpRequest, attempt_id: UUID) -> HttpResponseBase:
    correlation_id = get_request_correlation_id(request)
    if not request.user.is_authenticated:
        record_anonymous_download_denial(
            attempt_id=attempt_id,
            correlation_id=correlation_id,
        )
        return redirect_to_login(
            request.get_full_path(), str(settings.LOGIN_URL), REDIRECT_FIELD_NAME
        )
    try:
        download = open_generated_document_download(
            actor=request.user,
            attempt_id=attempt_id,
            correlation_id=correlation_id,
        )
    except (GeneratedDocumentDownloadNotFound, GeneratedDocumentDownloadUnavailable) as error:
        raise Http404("Requested content was not found.") from error

    response = FileResponse(download.source, content_type=DOCX_CONTENT_TYPE)
    response.headers["Content-Length"] = str(download.attempt.output_size)
    response.headers["Content-Disposition"] = build_content_disposition(
        download.attempt.output_filename
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
