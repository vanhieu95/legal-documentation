from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.core.correlation import (
    CORRELATION_ID_ATTRIBUTE,
    CORRELATION_ID_HEADER,
    resolve_correlation_id,
)


class RequestCorrelationMiddleware:
    """Attach a bounded correlation identifier to every request and response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        setattr(request, CORRELATION_ID_ATTRIBUTE, resolve_correlation_id(request))
        response = self.get_response(request)
        response.headers[CORRELATION_ID_HEADER] = getattr(request, CORRELATION_ID_ATTRIBUTE, "")
        return response
