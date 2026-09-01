from __future__ import annotations

from collections.abc import Callable

import pytest
from django.contrib.auth.models import User
from django.test import Client

from tests.factories import UserFactory


@pytest.fixture
def csrf_client() -> Client:
    """Return a client that exercises Django's real CSRF enforcement."""
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def user_factory() -> Callable[..., User]:
    """Return an explicit synthetic-user factory; no records are created automatically."""
    return UserFactory.create
