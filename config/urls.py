from __future__ import annotations

from django.urls import path

from apps.core.views import liveness, readiness

urlpatterns = [
    path("", liveness, name="placeholder"),
    path("health/live/", liveness, name="health-liveness"),
    path("health/ready/", readiness, name="health-readiness"),
]
