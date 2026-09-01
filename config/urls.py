from __future__ import annotations

from django.urls import path

from apps.core.views import component_gallery, liveness, readiness

urlpatterns = [
    path("", liveness, name="placeholder"),
    path("foundation/components/", component_gallery, name="component-gallery"),
    path("health/live/", liveness, name="health-liveness"),
    path("health/ready/", readiness, name="health-readiness"),
]
