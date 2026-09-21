from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_upgrade_from_cp_doc_e_creates_generation_table_on_linear_graph() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL migration profile.")
    previous = [("documents", "0002_add_document_drafts")]
    current = [("documents", "0003_generated_document")]
    executor = MigrationExecutor(connection)
    graph = executor.loader.graph
    assert graph.leaf_nodes("documents") == current

    try:
        executor.migrate(previous)
        assert "documents_generateddocument" not in connection.introspection.table_names()
        executor = MigrationExecutor(connection)
        executor.migrate(current)
        assert "documents_generateddocument" in connection.introspection.table_names()
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
