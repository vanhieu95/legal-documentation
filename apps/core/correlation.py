from __future__ import annotations

import re
import uuid
from typing import Final

from django.http import HttpRequest

CORRELATION_ID_HEADER: Final = "X-Correlation-ID"
CORRELATION_ID_ATTRIBUTE: Final = "correlation_id"
CORRELATION_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


def normalize_correlation_id(candidate: str | None) -> str | None:
    """Return a bounded correlation identifier or None when the value is unsafe."""
    if candidate is None:
        return None
    normalized = candidate.strip()
    if not normalized or len(normalized) > 128:
        return None
    if CORRELATION_ID_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def generate_correlation_id() -> str:
    """Create a new opaque correlation identifier."""
    return uuid.uuid4().hex


def resolve_correlation_id(request: HttpRequest) -> str:
    """Resolve the request correlation identifier from the header or a new value."""
    header_value = request.headers.get(CORRELATION_ID_HEADER)
    return normalize_correlation_id(header_value) or generate_correlation_id()


def get_request_correlation_id(request: HttpRequest) -> str:
    """Return the correlation identifier attached to the request."""
    correlation_id = getattr(request, CORRELATION_ID_ATTRIBUTE, None)
    if isinstance(correlation_id, str) and correlation_id:
        return correlation_id
    return resolve_correlation_id(request)
