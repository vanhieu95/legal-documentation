from __future__ import annotations

import pytest
from django.test import RequestFactory

from apps.core.correlation import (
    CORRELATION_ID_ATTRIBUTE,
    generate_correlation_id,
    get_request_correlation_id,
    normalize_correlation_id,
    resolve_correlation_id,
)


def test_normalize_correlation_id_accepts_bounded_values() -> None:
    assert normalize_correlation_id("synthetic-correlation-123") == "synthetic-correlation-123"


@pytest.mark.parametrize("candidate", ["", "short", "has space", "x" * 129, None])
def test_normalize_correlation_id_rejects_unsafe_values(candidate: str | None) -> None:
    assert normalize_correlation_id(candidate) is None


def test_resolve_correlation_id_uses_header_when_safe() -> None:
    request = RequestFactory().get("/", HTTP_X_CORRELATION_ID="synthetic-header-correlation")
    assert resolve_correlation_id(request) == "synthetic-header-correlation"


def test_resolve_correlation_id_generates_when_header_missing() -> None:
    request = RequestFactory().get("/")
    correlation_id = resolve_correlation_id(request)
    assert len(correlation_id) == 32


def test_get_request_correlation_id_prefers_attached_value() -> None:
    request = RequestFactory().get("/")
    setattr(request, CORRELATION_ID_ATTRIBUTE, "attached-correlation-value")
    assert get_request_correlation_id(request) == "attached-correlation-value"


def test_generate_correlation_id_is_opaque() -> None:
    first = generate_correlation_id()
    second = generate_correlation_id()
    assert first != second
    assert len(first) == 32
