from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.urls import path


def placeholder(request: HttpRequest) -> HttpResponse:
    return HttpResponse("OK", content_type="text/plain; charset=utf-8")


urlpatterns = [path("", placeholder, name="placeholder")]
