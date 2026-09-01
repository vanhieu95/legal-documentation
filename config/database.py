from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse


def parse_postgres_url(url: str) -> dict[str, object]:
    """Convert a PostgreSQL URL into Django's database configuration."""
    parsed = urlparse(url)
    database_name = parsed.path.removeprefix("/")
    hostname = parsed.hostname
    username = parsed.username
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or hostname is None
        or username is None
        or not database_name
    ):
        raise ValueError("A complete PostgreSQL database URL is required.")

    query = parse_qs(parsed.query, keep_blank_values=False)
    unsupported_options = set(query) - {"sslmode"}
    if unsupported_options:
        raise ValueError("The PostgreSQL database URL contains unsupported options.")

    settings: dict[str, object] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(database_name),
        "USER": unquote(username),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": hostname,
        "PORT": str(parsed.port or 5432),
    }
    if sslmode := query.get("sslmode"):
        settings["OPTIONS"] = {"sslmode": sslmode[-1]}

    return settings
