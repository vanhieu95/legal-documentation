from __future__ import annotations

from importlib import import_module

import pytest
from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.accounts.permissions import (
    ADMINISTRATOR_GROUP_NAME,
    APPLICATION_PERMISSION_CODENAMES,
)


@pytest.mark.django_db
def test_administrator_group_has_exactly_the_approved_permissions() -> None:
    administrator_group = Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)

    seeded_permissions = set(
        administrator_group.permissions.filter(content_type__app_label="accounts").values_list(
            "codename", flat=True
        )
    )

    assert seeded_permissions == set(APPLICATION_PERMISSION_CODENAMES)
    assert len(seeded_permissions) == 21


@pytest.mark.django_db
def test_permission_seeding_is_safely_repeatable() -> None:
    call_command("seed_administrator_permissions")
    call_command("seed_administrator_permissions")

    assert Group.objects.filter(name=ADMINISTRATOR_GROUP_NAME).count() == 1
    assert Permission.objects.filter(
        content_type__app_label="accounts",
        content_type__model="applicationaccess",
        codename__in=APPLICATION_PERMISSION_CODENAMES,
    ).count() == len(APPLICATION_PERMISSION_CODENAMES)


@pytest.mark.django_db(transaction=True)
def test_permission_seed_migration_is_reversible_without_deleting_users() -> None:
    executor = MigrationExecutor(connection)
    target = [("accounts", "0001_seed_administrator_permissions")]
    before = [("accounts", None)]

    executor.migrate(before)
    user = User.objects.create(username="synthetic-migration-user")

    executor = MigrationExecutor(connection)
    executor.migrate(target)
    assert Group.objects.filter(name=ADMINISTRATOR_GROUP_NAME).exists()

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    assert not Group.objects.filter(name=ADMINISTRATOR_GROUP_NAME).exists()
    assert User.objects.filter(pk=user.pk).exists()

    MigrationExecutor(connection).migrate(target)


@pytest.mark.django_db(transaction=True)
def test_reverse_migration_handles_preserved_members_and_an_absent_group() -> None:
    target = [("accounts", "0001_seed_administrator_permissions")]
    before = [("accounts", None)]
    MigrationExecutor(connection).migrate(before)
    MigrationExecutor(connection).migrate(target)
    user = User.objects.create(username="synthetic-preserved-member")
    group = Group.objects.get(name=ADMINISTRATOR_GROUP_NAME)
    user.groups.add(group)

    MigrationExecutor(connection).migrate(before)

    assert Group.objects.filter(name=ADMINISTRATOR_GROUP_NAME).exists()
    assert User.objects.filter(pk=user.pk).exists()

    MigrationExecutor(connection).migrate(target)
    Group.objects.get(name=ADMINISTRATOR_GROUP_NAME).delete()
    MigrationExecutor(connection).migrate(before)
    assert not Group.objects.filter(name=ADMINISTRATOR_GROUP_NAME).exists()

    migration = import_module("apps.accounts.migrations.0001_seed_administrator_permissions")
    with connection.schema_editor() as schema_editor:
        migration.unseed_permissions(apps, schema_editor)

    MigrationExecutor(connection).migrate(target)
