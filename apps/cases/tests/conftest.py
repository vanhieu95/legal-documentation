from __future__ import annotations

from collections.abc import Callable

import pytest

from apps.cases.models import Court, Entity, EntityAddress, Official
from tests.factories import CourtFactory, EntityAddressFactory, EntityFactory, OfficialFactory


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
