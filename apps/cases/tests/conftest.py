from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.cases.models import Court, Entity, EntityAddress, Official
from tests.factories import CourtFactory, EntityAddressFactory, EntityFactory, OfficialFactory


@pytest.fixture
def csrf_client() -> Client:
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def user_factory() -> Callable[..., User]:
    def create_user(**kwargs: Any) -> User:
        username = kwargs.pop("username", "synthetic-case-user")
        password = kwargs.pop("password", "synthetic-test-password")
        return User.objects.create_user(username=username, password=password, **kwargs)

    return create_user


@pytest.fixture
def court_factory() -> Callable[..., Court]:
    return CourtFactory.create


@pytest.fixture
def entity_factory() -> Callable[..., Entity]:
    return EntityFactory.create


@pytest.fixture
def address_factory() -> Callable[..., EntityAddress]:
    return EntityAddressFactory.create


@pytest.fixture
def official_factory() -> Callable[..., Official]:
    return OfficialFactory.create
