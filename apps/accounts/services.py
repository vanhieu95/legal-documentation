from __future__ import annotations

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.accounts.policies import application_access_policy
from apps.accounts.sessions import invalidate_user_sessions


@transaction.atomic
def change_password(*, actor: User, user: User, new_password: str) -> None:
    """Change a password and immediately invalidate every session for that user."""
    if actor.pk != user.pk and not application_access_policy.can_administer_accounts(actor):
        raise PermissionDenied
    validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    invalidate_user_sessions(user.pk)


@transaction.atomic
def complete_password_reset(*, user: User, new_password: str) -> None:
    """Complete an already-authorized reset and invalidate every user session."""
    validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    invalidate_user_sessions(user.pk)
