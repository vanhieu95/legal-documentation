from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_profile_applies_all_migrations() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL integration profile.")

    executor = MigrationExecutor(connection)

    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
    assert "django_migrations" in connection.introspection.table_names()
