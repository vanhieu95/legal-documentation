from __future__ import annotations

from collections.abc import Callable

import pytest
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.test import Client
from django.urls import path
from django.views.decorators.csrf import csrf_protect


@csrf_protect
def csrf_protected_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("synthetic response", content_type="text/plain")


urlpatterns = [path("synthetic-csrf/", csrf_protected_view)]


@pytest.mark.urls(__name__)
def test_csrf_client_rejects_a_post_without_a_token(csrf_client: Client) -> None:
    response = csrf_client.post("/synthetic-csrf/", {"value": "synthetic"})

    assert response.status_code == 403


@pytest.mark.django_db
def test_user_factory_creates_only_explicit_non_privileged_users(
    user_factory: Callable[..., User],
) -> None:
    assert User.objects.count() == 0

    user = user_factory()

    assert User.objects.count() == 1
    assert user.email.endswith("@example.invalid")
    assert user.check_password("synthetic-test-password")
    assert not user.is_staff
    assert not user.is_superuser
