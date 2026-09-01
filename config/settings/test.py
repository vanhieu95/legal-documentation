from __future__ import annotations

from config.settings.base import apply_base_settings

apply_base_settings(globals())

SECRET_KEY = "synthetic-test-secret-not-for-production"
DEBUG = False
ALLOWED_HOSTS = ["testserver"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
