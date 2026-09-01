from __future__ import annotations

from django.core.asgi import get_asgi_application
from django.core.management import get_commands
from django.core.wsgi import get_wsgi_application
from django.test import Client


def test_wsgi_and_asgi_entrypoints_load() -> None:
    assert get_wsgi_application() is not None
    assert get_asgi_application() is not None


def test_required_django_commands_are_available() -> None:
    commands = get_commands()

    assert {
        "check",
        "collectstatic",
        "compilemessages",
        "makemessages",
        "runserver",
    } <= commands.keys()


def test_root_is_a_non_disclosing_placeholder() -> None:
    response = Client().get("/")

    assert response.status_code == 200
    assert response.content == b"OK"
    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"
