from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db import OperationalError
from django.test import Client


def test_liveness_is_content_free_and_non_cacheable() -> None:
    response = Client().get("/health/live/")

    assert response.status_code == 200
    assert response.content == b"OK"
    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_reports_only_generic_availability() -> None:
    response = Client().get("/health/ready/")

    assert response.status_code == 200
    assert response.content == b"OK"
    assert response.headers["Cache-Control"] == "no-store"


def test_readiness_failure_does_not_disclose_database_details() -> None:
    with patch(
        "apps.core.views.connection.ensure_connection",
        side_effect=OperationalError("synthetic database path and credentials"),
    ):
        response = Client().get("/health/ready/")

    assert response.status_code == 503
    assert response.content == b"Unavailable"
    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert response.headers["Cache-Control"] == "no-store"
