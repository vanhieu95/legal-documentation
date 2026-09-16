from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import NoReturn, Protocol, cast

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import FileSystemStorage


class _PrivateStorageSettings(Protocol):
    PRIVATE_STORAGE_ROOT: str | Path


class _GroupIdStorage(Protocol):
    def _ensure_location_group_id(self, full_path: str) -> None: ...


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

    def save_immutable(self, name: str, content: File[bytes]) -> str:
        """Stage and atomically link a new file without an overwrite or partial final key."""
        full_path = Path(self.path(name))
        storage_root = Path(self.location).resolve()
        full_path.parent.mkdir(parents=True, exist_ok=True)
        current = full_path.parent
        while current != storage_root and storage_root in current.parents:
            current.chmod(self.directory_permissions_mode or 0o700)
            current = current.parent

        descriptor, staged_name = tempfile.mkstemp(
            prefix=".immutable-stage-",
            suffix=".tmp",
            dir=full_path.parent,
        )
        staged_path = Path(staged_name)
        try:
            with os.fdopen(descriptor, "wb") as staged:
                for chunk in content.chunks():
                    if not isinstance(chunk, bytes):
                        raise TypeError("Immutable private content must be binary.")
                    staged.write(chunk)
                staged.flush()
                os.fsync(staged.fileno())
            staged_path.chmod(self.file_permissions_mode or 0o600)
            os.link(staged_path, full_path)
            cast(_GroupIdStorage, self)._ensure_location_group_id(str(full_path))
        finally:
            staged_path.unlink(missing_ok=True)
        return name.replace("\\", "/")
