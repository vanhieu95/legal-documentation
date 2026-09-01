from __future__ import annotations

from config.settings.base import BASE_DIR, apply_base_settings

apply_base_settings(globals())

SECRET_KEY = "development-only-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
