from __future__ import annotations

from typing import TypedDict

from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext

from apps.accounts.policies import ApplicationPermission, application_access_policy


class NavigationItem(TypedDict):
    label: str
    url: str
    view_name: str


def application_shell(request: HttpRequest) -> dict[str, object]:
    """Build presentation-only navigation from the central server policy."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"application_navigation": (), "active_view_name": ""}

    navigation_contract = (
        (gettext("Dashboard"), "accounts:dashboard", ApplicationPermission.VIEW_CASES),
        (gettext("Cases"), "cases:list", ApplicationPermission.VIEW_CASES),
        (gettext("Templates"), "documents:templates", ApplicationPermission.VIEW_TEMPLATES),
        (gettext("Audit log"), "audit:list", ApplicationPermission.VIEW_AUDIT),
    )
    navigation: list[NavigationItem] = [
        {"label": label, "url": reverse(view_name), "view_name": view_name}
        for label, view_name, permission in navigation_contract
        if application_access_policy.has_permission(user, permission)
    ]
    active_view_name = request.resolver_match.view_name if request.resolver_match else ""
    return {
        "application_navigation": navigation,
        "active_view_name": active_view_name,
    }
