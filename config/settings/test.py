from __future__ import annotations

import os

from config.database import parse_postgres_url
from config.settings.base import apply_base_settings

apply_base_settings(globals())

SECRET_KEY = "synthetic-test-secret-not-for-production"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
if test_database_url := os.environ.get("TEST_DATABASE_URL"):
    DATABASES = {"default": parse_postgres_url(test_database_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
