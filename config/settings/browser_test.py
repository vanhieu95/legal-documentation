from __future__ import annotations

from pathlib import Path

from config.settings.base import apply_base_settings

apply_base_settings(globals())

SECRET_KEY = "synthetic-browser-test-secret-not-for-production"
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path("/tmp/vds-browser-test.sqlite3"),
    }
}
