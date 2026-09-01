from __future__ import annotations

from pathlib import Path
from typing import NoReturn, Protocol, cast

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class _PrivateStorageSettings(Protocol):
    PRIVATE_STORAGE_ROOT: str | Path


class PrivateFileSystemStorage(FileSystemStorage):
    """Filesystem storage that never exposes a direct public URL."""

    def __init__(self, location: str | Path | None = None) -> None:
        configured_settings = cast(_PrivateStorageSettings, settings)
        super().__init__(
            location=location if location is not None else configured_settings.PRIVATE_STORAGE_ROOT,
            base_url=None,
            file_permissions_mode=0o600,
            directory_permissions_mode=0o700,
            allow_overwrite=False,
        )

    def url(self, name: str | None) -> NoReturn:
        raise ValueError("Private files are not accessible via a URL.")
