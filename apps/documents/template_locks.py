from __future__ import annotations

from django.db import connection


def acquire_template_type_lock(type_key: str) -> None:
    """Serialize template activation and reservation for one registered type."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [type_key])
