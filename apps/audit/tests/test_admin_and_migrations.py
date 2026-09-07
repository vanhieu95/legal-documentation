from __future__ import annotations

import importlib
import pkgutil

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client

from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.admin import AuditEventAdmin
from apps.audit.models import AuditEvent
from apps.audit.recorder import AuditTarget, record_audit_event


@pytest.fixture
def actor(user_factory: object) -> User:
    assert callable(user_factory)
    return user_factory(username="synthetic-audit-admin-actor")


@pytest.mark.django_db
def test_audit_admin_is_read_only(actor: User) -> None:
    event = record_audit_event(
        action=AuditAction.IDENTITY_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor=actor,
        target=AuditTarget(type=AuditTargetType.USER, id=str(actor.pk)),
        correlation_id="synthetic-correlation-admin",
    )
    model_admin = AuditEventAdmin(AuditEvent, admin.site)
    request = type("Request", (), {"user": actor})()

    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_change_permission(request, event) is False
    assert model_admin.has_delete_permission(request, event) is False


@pytest.mark.django_db
def test_audit_app_imports_no_business_domain_models() -> None:
    prohibited_modules = ("apps.cases", "apps.documents")
    import apps.audit as audit_package

    for module_info in pkgutil.walk_packages(
        audit_package.__path__, prefix=f"{audit_package.__name__}."
    ):
        module = importlib.import_module(module_info.name)
        module_source = getattr(module, "__file__", "") or ""
        if module_source.endswith("migrations/__init__.py"):
            continue
        for prohibited in prohibited_modules:
            assert prohibited not in module.__dict__


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_audit_event_migration_indexes_exist() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL integration profile.")

    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []

    table_name = AuditEvent._meta.db_table
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table_name)
    index_columns = {
        tuple(details["columns"])
        for details in constraints.values()
        if details["index"] or details["unique"]
    }

    assert ("occurred_at",) in index_columns
    assert ("action",) in index_columns
    assert ("outcome",) in index_columns
    assert ("correlation_id",) in index_columns
    assert ("target_type", "target_id") in index_columns


@pytest.mark.django_db
def test_correlation_middleware_attaches_and_returns_header(client: Client) -> None:
    response = client.get("/", HTTP_X_CORRELATION_ID="synthetic-request-correlation")

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "synthetic-request-correlation"
