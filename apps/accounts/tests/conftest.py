from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import Client


@pytest.fixture
def csrf_client() -> Client:
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def user_factory() -> Callable[..., User]:
    def create_user(**kwargs: Any) -> User:
        username = kwargs.pop("username", "synthetic-account-user")
        password = kwargs.pop("password", "synthetic-test-password")
        return User.objects.create_user(username=username, password=password, **kwargs)

    return create_user
