from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone, translation

from config.environment import parse_allowed_hosts, parse_trusted_origins

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ENVIRONMENT_NAMES = {
    "DATABASE_URL",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "DJANGO_PRIVATE_STORAGE_ROOT",
    "DJANGO_SECRET_KEY",
    "DJANGO_STATIC_ROOT",
}


def test_settings_are_split_by_environment() -> None:
    settings_directory = PROJECT_ROOT / "config" / "settings"

    assert not (PROJECT_ROOT / "config" / "settings.py").exists()
    assert {
        "__init__.py",
        "base.py",
        "development.py",
        "production.py",
        "test.py",
    } <= {path.name for path in settings_directory.iterdir()}


def test_vietnamese_locale_and_middleware_order_are_explicit() -> None:
    base = importlib.import_module("config.settings.base")
    middleware = base.MIDDLEWARE

    assert base.LANGUAGE_CODE == "vi"
    assert base.LANGUAGES == [("vi", "Tiếng Việt")]
    assert base.TIME_ZONE == "Asia/Ho_Chi_Minh"
    assert base.USE_I18N is True
    assert base.USE_TZ is True
    assert middleware.index(
        "django.contrib.sessions.middleware.SessionMiddleware"
    ) < middleware.index("django.middleware.locale.LocaleMiddleware")
    assert middleware.index("django.middleware.locale.LocaleMiddleware") < middleware.index(
        "django.middleware.common.CommonMiddleware"
    )


def test_test_runtime_uses_aware_utc_storage_and_ho_chi_minh_presentation() -> None:
    instant = datetime(2026, 1, 1, tzinfo=UTC)

    assert settings.USE_TZ is True
    assert timezone.is_aware(timezone.now())
    assert timezone.localtime(instant).isoformat() == "2026-01-01T07:00:00+07:00"
    with translation.override("vi"):
        assert translation.get_language() == "vi"


def test_private_and_static_storage_roots_are_disjoint() -> None:
    private_root = Path(settings.PRIVATE_STORAGE_ROOT).resolve()
    public_roots = [Path(settings.STATIC_ROOT).resolve()]
    public_roots.extend(Path(path).resolve() for path in settings.STATICFILES_DIRS)

    for public_root in public_roots:
        assert not private_root.is_relative_to(public_root)
        assert not public_root.is_relative_to(private_root)


@pytest.mark.parametrize(
    ("parser", "value"),
    [
        (parse_allowed_hosts, "*.internal"),
        (parse_trusted_origins, "https://*.internal"),
    ],
)
def test_production_hosts_and_origins_reject_wildcards(
    parser: Callable[[str], list[str]], value: str
) -> None:
    with pytest.raises(ImproperlyConfigured):
        parser(value)


def _production_environment() -> dict[str, str]:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(PROJECT_ROOT),
    }
    environment.update(
        {
            "DATABASE_URL": (
                "postgresql://vds_app:synthetic@127.0.0.1:5432/vds_documents?sslmode=require"
            ),
            "DJANGO_ALLOWED_HOSTS": "app.internal",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.internal",
            "DJANGO_PRIVATE_STORAGE_ROOT": "/tmp/vds-private-synthetic",
            "DJANGO_SECRET_KEY": "synthetic-only-" + ("x" * 64),
            "DJANGO_STATIC_ROOT": "/tmp/vds-static-synthetic",
        }
    )
    return environment


def test_production_settings_fail_closed_when_required_values_are_missing() -> None:
    environment = _production_environment()
    for name in PRODUCTION_ENVIRONMENT_NAMES:
        environment.pop(name, None)

    result = subprocess.run(
        [sys.executable, "-c", "import config.settings.production"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "Missing required production environment variables" in result.stderr


def test_complete_production_environment_loads_secure_postgres_settings() -> None:
    script = """
import importlib
import json

module = importlib.import_module("config.settings.production")
print(json.dumps({
    "allowed_hosts": module.ALLOWED_HOSTS,
    "csrf_origins": module.CSRF_TRUSTED_ORIGINS,
    "database_engine": module.DATABASES["default"]["ENGINE"],
    "debug": module.DEBUG,
    "private_root": str(module.PRIVATE_STORAGE_ROOT),
    "static_root": str(module.STATIC_ROOT),
}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=_production_environment(),
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.stderr == ""
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "allowed_hosts": ["app.internal"],
        "csrf_origins": ["https://app.internal"],
        "database_engine": "django.db.backends.postgresql",
        "debug": False,
        "private_root": "/tmp/vds-private-synthetic",
        "static_root": "/tmp/vds-static-synthetic",
    }
