from __future__ import annotations

from typing import Any

from django import template
from django.contrib.auth.models import AnonymousUser, User

from apps.accounts.policies import ApplicationPermission, application_access_policy

register = template.Library()


@register.simple_tag(takes_context=True)
def has_application_permission(context: dict[str, Any], permission: str) -> bool:
    """Mirror permission state for presentation; server enforcement remains mandatory."""
    actor = context.get("user")
    if not isinstance(actor, (User, AnonymousUser)):
        return False
    try:
        required_permission = ApplicationPermission(permission)
    except ValueError:
        return False
    return application_access_policy.has_permission(actor, required_permission)
