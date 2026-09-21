from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol, cast

from django.conf import settings
from django.core.files.storage import Storage, storages
from django.utils import timezone

from apps.core.correlation import generate_correlation_id
from apps.core.storage import PrivateFileSystemStorage
from apps.documents.models import GeneratedDocument, TemplateVersion

_READ_CHUNK_BYTES = 64 * 1024
STALE_STAGING_AGE = timedelta(hours=24)
_STAGING_NAME = re.compile(r"^\.immutable-stage-[A-Za-z0-9_-]+\.tmp$")


class PrivateStorageConfigurationError(RuntimeError):
    """The reconciliation target is not the configured private filesystem root."""


class _PrivateStorageSettings(Protocol):
    PRIVATE_STORAGE_ROOT: str | Path


@dataclass(frozen=True, slots=True)
class _StoredReference:
    kind: Literal["template", "artifact"]
    key: str
    byte_size: int
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class PrivateFileReconciliationReport:
    status: Literal["ok", "integrity_breach"]
    correlation_id: str
    completed_at: datetime
    duration_ms: int
    counts: Mapping[str, int]

    def as_event(self) -> dict[str, object]:
        return {
            "event": "private_file_reconciliation_completed",
            "status": self.status,
            "severity": "error" if self.status == "integrity_breach" else "info",
            "correlation_id": self.correlation_id,
            "timestamp": self.completed_at.isoformat(),
            "duration_ms": self.duration_ms,
            "counts": dict(self.counts),
        }


def _template_references() -> Iterator[_StoredReference]:
    rows = TemplateVersion.objects.values_list(
        "storage_key", "byte_size", "checksum_sha256"
    ).iterator(chunk_size=2_000)
    for storage_key, byte_size, checksum_sha256 in rows:
        yield _StoredReference(
            kind="template",
            key=storage_key,
            byte_size=byte_size,
            checksum_sha256=checksum_sha256,
        )


def _artifact_references() -> Iterator[_StoredReference]:
    rows = (
        GeneratedDocument.objects.filter(status=GeneratedDocument.Status.GENERATED)
        .values_list("output_storage_key", "output_size", "output_checksum_sha256")
        .iterator(chunk_size=2_000)
    )
    for storage_key, byte_size, checksum_sha256 in rows:
        yield _StoredReference(
            kind="artifact",
            key=storage_key,
            byte_size=cast(int, byte_size),
            checksum_sha256=checksum_sha256,
        )


def _verify_reference(
    reference: _StoredReference,
    *,
    storage: Storage,
    private_root: Path,
    counts: dict[str, int],
) -> None:
    plural = "templates" if reference.kind == "template" else "artifacts"
    try:
        candidate = Path(storage.path(reference.key))
        relative = candidate.relative_to(private_root)
        current = private_root
        for part in relative.parts:
            current /= part
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                break
            if stat.S_ISLNK(metadata.st_mode):
                counts["storage_errors"] += 1
                return
        if not storage.exists(reference.key):
            counts[f"{plural}_missing"] += 1
            return
        digest = hashlib.sha256()
        byte_size = 0
        with storage.open(reference.key, "rb") as source:
            for chunk in source.chunks(chunk_size=_READ_CHUNK_BYTES):
                if not isinstance(chunk, bytes):
                    raise TypeError("Private storage returned non-binary content.")
                digest.update(chunk)
                byte_size += len(chunk)
    except FileNotFoundError:
        counts[f"{plural}_missing"] += 1
        return
    except Exception:
        counts["storage_errors"] += 1
        return

    if byte_size != reference.byte_size or not hmac.compare_digest(
        digest.hexdigest(), reference.checksum_sha256
    ):
        counts[f"{plural}_modified"] += 1


def _validated_private_root(storage: Storage) -> Path:
    if not isinstance(storage, PrivateFileSystemStorage):
        raise PrivateStorageConfigurationError(
            "Private file reconciliation requires the configured private filesystem storage."
        )
    configured_settings = cast(_PrivateStorageSettings, settings)
    configured_root = Path(configured_settings.PRIVATE_STORAGE_ROOT).resolve()
    storage_root = Path(storage.location).resolve()
    if storage_root != configured_root:
        raise PrivateStorageConfigurationError(
            "Private file reconciliation storage does not match the configured private root."
        )
    if storage_root.exists() and not storage_root.is_dir():
        raise PrivateStorageConfigurationError(
            "The configured private storage root is not a directory."
        )
    return storage_root


def _inventory_private_root(
    *,
    private_root: Path,
    expected_keys: set[str],
    cleanup_stale_staging: bool,
    stale_before: float,
    counts: dict[str, int],
) -> None:
    if not private_root.exists():
        return
    pending = [private_root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        counts["unsafe_entries"] += 1
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        counts["unsafe_entries"] += 1
                        continue
                    path = Path(entry.path)
                    key = path.relative_to(private_root).as_posix()
                    namespace = key.partition("/")[0]
                    if namespace in {"templates", "generated"} and _STAGING_NAME.fullmatch(
                        entry.name
                    ):
                        counts["staging_files"] += 1
                        try:
                            metadata = entry.stat(follow_symlinks=False)
                        except OSError:
                            counts["inventory_errors"] += 1
                            continue
                        if metadata.st_mtime > stale_before:
                            continue
                        counts["stale_staging_files"] += 1
                        if not cleanup_stale_staging:
                            continue
                        try:
                            current = path.lstat()
                            if not stat.S_ISREG(current.st_mode) or current.st_mtime > stale_before:
                                counts["cleanup_errors"] += 1
                                continue
                            path.unlink()
                            counts["staging_files_removed"] += 1
                        except OSError:
                            counts["cleanup_errors"] += 1
                        continue
                    if key not in expected_keys:
                        counts["orphaned_files"] += 1
        except OSError:
            counts["inventory_errors"] += 1


def reconcile_private_files(
    *,
    storage: Storage | None = None,
    cleanup_stale_staging: bool = False,
) -> PrivateFileReconciliationReport:
    """Verify every database-referenced private template and generated artifact."""
    started_at = time.monotonic()
    private_storage = storage or storages["private"]
    private_root = _validated_private_root(private_storage)
    expected_keys: set[str] = set()
    counts = {
        "templates_checked": 0,
        "artifacts_checked": 0,
        "templates_missing": 0,
        "templates_modified": 0,
        "artifacts_missing": 0,
        "artifacts_modified": 0,
        "storage_errors": 0,
        "orphaned_files": 0,
        "staging_files": 0,
        "stale_staging_files": 0,
        "staging_files_removed": 0,
        "unsafe_entries": 0,
        "inventory_errors": 0,
        "cleanup_errors": 0,
        "integrity_breaches": 0,
    }

    for reference in _template_references():
        counts["templates_checked"] += 1
        expected_keys.add(reference.key)
        _verify_reference(
            reference,
            storage=private_storage,
            private_root=private_root,
            counts=counts,
        )
    for reference in _artifact_references():
        counts["artifacts_checked"] += 1
        expected_keys.add(reference.key)
        _verify_reference(
            reference,
            storage=private_storage,
            private_root=private_root,
            counts=counts,
        )

    stale_before = time.time() - STALE_STAGING_AGE.total_seconds()
    _inventory_private_root(
        private_root=private_root,
        expected_keys=expected_keys,
        cleanup_stale_staging=cleanup_stale_staging,
        stale_before=stale_before,
        counts=counts,
    )

    counts["integrity_breaches"] = sum(
        counts[category]
        for category in (
            "templates_missing",
            "templates_modified",
            "artifacts_missing",
            "artifacts_modified",
            "storage_errors",
            "orphaned_files",
            "unsafe_entries",
            "inventory_errors",
            "cleanup_errors",
        )
    )
    stale_staging_remaining = counts["stale_staging_files"] - counts["staging_files_removed"]
    counts["integrity_breaches"] += stale_staging_remaining
    duration_ms = max(0, round((time.monotonic() - started_at) * 1_000))
    status: Literal["ok", "integrity_breach"] = (
        "integrity_breach" if counts["integrity_breaches"] else "ok"
    )
    return PrivateFileReconciliationReport(
        status=status,
        correlation_id=generate_correlation_id(),
        completed_at=timezone.now(),
        duration_ms=duration_ms,
        counts=counts,
    )
