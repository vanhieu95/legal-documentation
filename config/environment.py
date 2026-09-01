from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def require_environment(names: Iterable[str]) -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        raise ImproperlyConfigured(
            "Missing required production environment variables: " + ", ".join(missing)
        )
    return values


def parse_allowed_hosts(value: str) -> list[str]:
    hosts = [host.strip() for host in value.split(",") if host.strip()]
    if not hosts or any("*" in host or "://" in host or "/" in host for host in hosts):
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain explicit host names.")
    return hosts


def parse_trusted_origins(value: str) -> list[str]:
    origins = [origin.strip() for origin in value.split(",") if origin.strip()]
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or "*" in parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ImproperlyConfigured(
                "DJANGO_CSRF_TRUSTED_ORIGINS must contain explicit HTTPS origins."
            )
    if not origins:
        raise ImproperlyConfigured(
            "DJANGO_CSRF_TRUSTED_ORIGINS must contain explicit HTTPS origins."
        )
    return origins


def parse_absolute_path(value: str, setting_name: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ImproperlyConfigured(f"{setting_name} must be an absolute path.")
    return path


def paths_overlap(left: Path, right: Path) -> bool:
    resolved_left = left.resolve()
    resolved_right = right.resolve()
    return resolved_left.is_relative_to(resolved_right) or resolved_right.is_relative_to(
        resolved_left
    )
