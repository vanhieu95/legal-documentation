"""Create deterministic synthetic principals for the local browser-test database."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.browser_test")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from django.contrib.sessions.models import Session  # noqa: E402

from apps.accounts.permissions import seed_administrator_permissions  # noqa: E402

if settings.SETTINGS_MODULE != "config.settings.browser_test":
    raise RuntimeError("Browser fixtures may only be created with browser-test settings.")

administrator_group = seed_administrator_permissions()
Session.objects.all().delete()


def replace_synthetic_user(
    username: str,
    password: str,
    *,
    is_superuser: bool = False,
    is_staff: bool = False,
) -> User:
    user, _created = User.objects.get_or_create(username=username)
    user.is_active = True
    user.is_superuser = is_superuser
    user.is_staff = is_staff
    user.set_password(password)
    user.save()
    user.groups.clear()
    return user


administrator = replace_synthetic_user(
    "synthetic-browser-administrator",
    "synthetic-browser-password-123!",
)
administrator.groups.add(administrator_group)

replace_synthetic_user(
    "synthetic-browser-superuser",
    "synthetic-browser-password-123!",
    is_superuser=True,
    is_staff=True,
)

replace_synthetic_user(
    "synthetic-browser-non-administrator",
    "synthetic-browser-password-123!",
)
