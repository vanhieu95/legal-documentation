from __future__ import annotations

from django.contrib.auth.models import Group, Permission, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.accounts.audit import (
    record_identity_account_activated,
    record_identity_account_deactivated,
    record_identity_group_changed,
    record_identity_password_changed,
    record_identity_password_reset,
    record_identity_permission_changed,
    serialize_group_names,
    serialize_permission_codenames,
)
from apps.accounts.policies import application_access_policy
from apps.accounts.sessions import invalidate_user_sessions


@transaction.atomic
def change_password(*, actor: User, user: User, new_password: str, correlation_id: str) -> None:
    """Change a password and immediately invalidate every session for that user."""
    if actor.pk != user.pk and not application_access_policy.can_administer_accounts(actor):
        raise PermissionDenied
    validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    invalidate_user_sessions(user.pk)
    record_identity_password_changed(actor=actor, user=user, correlation_id=correlation_id)


@transaction.atomic
def complete_password_reset(*, user: User, new_password: str, correlation_id: str) -> None:
    """Complete an already-authorized reset and invalidate every user session."""
    validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    invalidate_user_sessions(user.pk)
    record_identity_password_reset(user=user, correlation_id=correlation_id)


@transaction.atomic
def activate_account(*, actor: User, user: User, correlation_id: str) -> None:
    """Activate an account through the superuser-only administration boundary."""
    application_access_policy.require_account_administration(actor)
    if user.is_active:
        return
    user.is_active = True
    user.save(update_fields=["is_active"])
    record_identity_account_activated(actor=actor, user=user, correlation_id=correlation_id)


@transaction.atomic
def deactivate_account(*, actor: User, user: User, correlation_id: str) -> None:
    """Deactivate an account through the superuser-only administration boundary."""
    application_access_policy.require_account_administration(actor)
    if not user.is_active:
        return
    user.is_active = False
    user.save(update_fields=["is_active"])
    invalidate_user_sessions(user.pk)
    record_identity_account_deactivated(actor=actor, user=user, correlation_id=correlation_id)


@transaction.atomic
def set_group_memberships(
    *,
    actor: User,
    user: User,
    groups: list[Group],
    correlation_id: str,
) -> None:
    """Replace a user's group memberships through the superuser-only boundary."""
    application_access_policy.require_account_administration(actor)
    previous_groups = serialize_group_names(list(user.groups.all()))
    user.groups.set(groups)
    current_groups = serialize_group_names(groups)
    if previous_groups != current_groups:
        record_identity_group_changed(
            actor=actor,
            user=user,
            correlation_id=correlation_id,
            changed_fields=["groups"],
        )


@transaction.atomic
def set_user_permissions(
    *,
    actor: User,
    user: User,
    permissions: list[Permission],
    correlation_id: str,
) -> None:
    """Replace a user's direct permissions through the superuser-only boundary."""
    application_access_policy.require_account_administration(actor)
    previous_permissions = serialize_permission_codenames(list(user.user_permissions.all()))
    user.user_permissions.set(permissions)
    current_permissions = serialize_permission_codenames(permissions)
    if previous_permissions != current_permissions:
        record_identity_permission_changed(
            actor=actor,
            user=user,
            correlation_id=correlation_id,
            changed_fields=["user_permissions"],
        )
