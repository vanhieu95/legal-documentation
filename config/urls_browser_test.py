"""Browser-test-only routes for exercising global error handlers end to end."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.urls import path

from config.urls import urlpatterns as application_urlpatterns


def forbidden_fixture(_request: HttpRequest) -> HttpResponse:
    raise PermissionDenied("synthetic-browser-sensitive-detail")


def error_fixture(_request: HttpRequest) -> HttpResponse:
    raise RuntimeError("synthetic-browser-sensitive-detail")


urlpatterns = [
    *application_urlpatterns,
    path("browser-test/forbidden/", forbidden_fixture),
    path("browser-test/error/", error_fixture),
]

handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"
