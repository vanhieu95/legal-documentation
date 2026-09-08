from __future__ import annotations

from typing import Any

import factory
from django.contrib.auth.models import User
from factory.django import DjangoModelFactory

from apps.cases.models import CaseRecord, Court, Entity, EntityAddress, Official


class UserFactory(DjangoModelFactory[User]):
    """Create synthetic, non-privileged users with usable test-only passwords."""

    class Meta:
        model = User

    username = factory.Sequence(lambda number: f"synthetic-user-{number}")
    email = factory.LazyAttribute(lambda user: f"{user.username}@example.invalid")
    password = "synthetic-test-password"
    is_staff = False
    is_superuser = False

    @classmethod
    def _create(cls, model_class: type[User], *args: Any, **kwargs: Any) -> User:
        return model_class.objects.create_user(*args, **kwargs)


class CourtFactory(DjangoModelFactory[Court]):
    """Create a synthetic court without using real operational data."""

    class Meta:
        model = Court

    code = factory.Sequence(lambda number: f"SYN-COURT-{number:04d}")
    full_name = factory.Sequence(lambda number: f"Synthetic People's Court {number}")
    short_name = factory.Sequence(lambda number: f"Synthetic Court {number}")
    level = Court.Level.DISTRICT
    address = factory.Sequence(lambda number: f"Synthetic administrative address {number}")


class EntityFactory(DjangoModelFactory[Entity]):
    """Create a synthetic individual with an explicitly fake identifier."""

    class Meta:
        model = Entity

    kind = Entity.Kind.INDIVIDUAL
    legal_name = factory.Sequence(lambda number: f"Synthetic Person {number}")
    display_name = factory.Sequence(lambda number: f"Person {number}")
    identity_document_number = factory.Sequence(lambda number: f"SYN-ID-{number:04d}")


class EntityAddressFactory(DjangoModelFactory[EntityAddress]):
    """Create a synthetic current address for a synthetic entity."""

    class Meta:
        model = EntityAddress

    entity = factory.SubFactory(EntityFactory)
    kind = EntityAddress.Kind.CURRENT
    full_address = factory.Sequence(lambda number: f"Synthetic address {number}")


class OfficialFactory(DjangoModelFactory[Official]):
    """Create a synthetic official attached to synthetic reference records."""

    class Meta:
        model = Official

    entity = factory.SubFactory(EntityFactory)
    home_court = factory.SubFactory(CourtFactory)
    title = "Judge"
    position = "Civil division"


class CaseRecordFactory(DjangoModelFactory[CaseRecord]):
    """Create a synthetic incomplete pre-acceptance case."""

    class Meta:
        model = CaseRecord

    internal_reference = factory.Sequence(lambda number: f"SYN-CASE-{number:06d}")
    court = factory.SubFactory(CourtFactory)
    matter_type = "Synthetic civil matter"
    procedural_stage = CaseRecord.ProceduralStage.PRE_ACCEPTANCE
    created_by = factory.SubFactory(UserFactory)
    last_edited_by = factory.SelfAttribute("created_by")
