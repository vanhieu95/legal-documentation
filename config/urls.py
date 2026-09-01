from __future__ import annotations

from django.urls import include, path

from apps.core.views import component_gallery, liveness, readiness

urlpatterns = [
    path("", include("apps.accounts.urls")),
    path("", liveness, name="placeholder"),
    path("foundation/components/", component_gallery, name="component-gallery"),
    path("health/live/", liveness, name="health-liveness"),
    path("health/ready/", readiness, name="health-readiness"),
]

handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
