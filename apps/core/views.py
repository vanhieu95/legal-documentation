from __future__ import annotations

from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


def _health_response(content: str, *, status: int = 200) -> HttpResponse:
    response = HttpResponse(content, content_type="text/plain; charset=utf-8", status=status)
    response.headers["Cache-Control"] = "no-store"
    return response


@require_GET
def liveness(request: HttpRequest) -> HttpResponse:
    return _health_response("OK")


@require_GET
def readiness(request: HttpRequest) -> HttpResponse:
    try:
        connection.ensure_connection()
    except DatabaseError:
        return _health_response("Unavailable", status=503)
    return _health_response("OK")


@require_GET
def component_gallery(request: HttpRequest) -> HttpResponse:
    """Render only the shared presentation primitives used by later application pages."""
    return render(request, "foundation/component_gallery.html")


def permission_denied(request: HttpRequest, exception: Exception) -> HttpResponse:
    return render(request, "errors/403.html", status=403)


def page_not_found(request: HttpRequest, exception: Exception) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def server_error(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)
