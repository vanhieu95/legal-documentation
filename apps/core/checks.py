from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, cast

from django.apps import AppConfig
from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, register

from config.environment import paths_overlap


class _StorageBoundarySettings(Protocol):
    PRIVATE_STORAGE_ROOT: str | Path
    STATIC_ROOT: str | Path
    STATICFILES_DIRS: Iterable[str | Path]


@register(Tags.security, deploy=True)
def check_private_storage_boundaries(
    app_configs: Iterable[AppConfig] | None, **kwargs: object
) -> list[CheckMessage]:
    configured_settings = cast(_StorageBoundarySettings, settings)
    private_root = Path(configured_settings.PRIVATE_STORAGE_ROOT)
    public_roots = [Path(configured_settings.STATIC_ROOT)]
    public_roots.extend(Path(path) for path in configured_settings.STATICFILES_DIRS)
    if any(paths_overlap(private_root, public_root) for public_root in public_roots):
        return [
            Error(
                "Private storage overlaps a static file root.",
                hint="Configure distinct, non-nested private and static storage roots.",
                id="core.E001",
            )
        ]
    return []
