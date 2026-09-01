from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from config.database import parse_postgres_url
from config.environment import (
    parse_absolute_path,
    parse_allowed_hosts,
    parse_trusted_origins,
    paths_overlap,
    require_environment,
)
from config.settings.base import apply_base_settings, storage_configuration

apply_base_settings(globals())

_environment = require_environment(
    {
        "DATABASE_URL",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "DJANGO_PRIVATE_STORAGE_ROOT",
        "DJANGO_SECRET_KEY",
        "DJANGO_STATIC_ROOT",
    }
)

SECRET_KEY = _environment["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = parse_allowed_hosts(_environment["DJANGO_ALLOWED_HOSTS"])
CSRF_TRUSTED_ORIGINS = parse_trusted_origins(_environment["DJANGO_CSRF_TRUSTED_ORIGINS"])

try:
    DATABASES = {"default": parse_postgres_url(_environment["DATABASE_URL"])}
except ValueError as error:
    raise ImproperlyConfigured("DATABASE_URL must be a complete PostgreSQL URL.") from error

PRIVATE_STORAGE_ROOT = parse_absolute_path(
    _environment["DJANGO_PRIVATE_STORAGE_ROOT"], "DJANGO_PRIVATE_STORAGE_ROOT"
)
STATIC_ROOT = parse_absolute_path(_environment["DJANGO_STATIC_ROOT"], "DJANGO_STATIC_ROOT")
if paths_overlap(PRIVATE_STORAGE_ROOT, STATIC_ROOT):
    raise ImproperlyConfigured("Production private and static storage roots must be separate.")
STORAGES = storage_configuration()

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
