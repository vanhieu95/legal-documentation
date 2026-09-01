from __future__ import annotations

import pytest

from config.database import parse_postgres_url


def test_postgres_url_is_parsed_into_django_connection_settings() -> None:
    settings = parse_postgres_url(
        "postgresql://vds_user:p%40ss@db.internal:5433/vds_documents?sslmode=require"
    )

    assert settings == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "vds_documents",
        "USER": "vds_user",
        "PASSWORD": "p@ss",
        "HOST": "db.internal",
        "PORT": "5433",
        "OPTIONS": {"sslmode": "require"},
    }


@pytest.mark.parametrize("url", ["", "mysql://user:pass@db/name", "postgresql:///missing-host"])
def test_invalid_postgres_url_is_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        parse_postgres_url(url)
