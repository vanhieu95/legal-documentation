from __future__ import annotations

import factory
from django.contrib.auth.models import User
from factory.django import DjangoModelFactory


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
    def _create(cls, model_class: type[User], *args: object, **kwargs: object) -> User:
        return model_class.objects.create_user(*args, **kwargs)
