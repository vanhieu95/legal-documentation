from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from django.core.files.base import ContentFile, File
from django.core.files.storage import Storage, storages
from django.core.management import CommandError, call_command
from django.db import models
from django.utils import timezone

from apps.cases.models import CaseRecord
from apps.core.storage import PrivateFileSystemStorage
from apps.documents import reconciliation
from apps.documents.management.commands import reconcile_private_files as reconciliation_command
from apps.documents.models import GeneratedDocument, TemplateVersion
from apps.documents.reconciliation import (
    PrivateStorageConfigurationError,
    reconcile_private_files,
)
from apps.documents.storage_keys import build_generated_storage_key, build_template_storage_key
from apps.documents.tests.test_template_versions import template_values
from tests.factories import CaseRecordFactory

pytestmark = pytest.mark.django_db


class _StorageHandlerCache:
    _storages: dict[str, Storage]


@pytest.fixture(autouse=True)
def _isolated_private_storage(settings: Any, tmp_path: Path) -> Iterator[Path]:
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"
    cast(_StorageHandlerCache, storages)._storages.clear()
    yield Path(settings.PRIVATE_STORAGE_ROOT)
    cast(_StorageHandlerCache, storages)._storages.clear()


def _stored_records(user_factory: object) -> tuple[TemplateVersion, GeneratedDocument]:
    actor = cast(Any, user_factory)(username=f"reconciliation-{uuid4().hex[:8]}")
    case = cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))
    template_content = b"synthetic-template-package"
    template_key = build_template_storage_key("synthetic-platform-test", "reconcile-v1")
    assert storages["private"].save(template_key, ContentFile(template_content)) == template_key
    template = TemplateVersion.objects.create(
        **template_values(
            uploader=actor,
            version="reconcile-v1",
            storage_key=template_key,
            checksum_sha256=hashlib.sha256(template_content).hexdigest(),
            byte_size=len(template_content),
        )
    )

    attempt = GeneratedDocument.objects.create(
        case=case,
        type_key=template.type_key,
        template_version=template,
        schema_version="v1",
        source_draft_id=uuid4(),
        case_revision=case.revision,
        draft_revision=1,
        input_snapshot={"version": 1, "values": {}},
        resolved_values_snapshot={"version": 1, "values": {}},
        override_snapshot={"version": 1, "values": {}},
        template_snapshot={
            "version": 1,
            "identity": {
                "id": str(template.pk),
                "type_key": template.type_key,
                "version": template.version,
                "checksum_sha256": template.checksum_sha256,
            },
        },
        actor=actor,
        idempotency_key_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
    )
    artifact_content = b"synthetic-generated-package"
    artifact_key = build_generated_storage_key(case.pk, attempt.pk)
    assert storages["private"].save(artifact_key, ContentFile(artifact_content)) == artifact_key
    models.QuerySet.update(
        GeneratedDocument.objects.filter(pk=attempt.pk),
        status=GeneratedDocument.Status.GENERATED,
        generated_at=timezone.now(),
        output_storage_key=artifact_key,
        output_filename="synthetic.docx",
        output_size=len(artifact_content),
        output_checksum_sha256=hashlib.sha256(artifact_content).hexdigest(),
    )
    return template, GeneratedDocument.objects.get(pk=attempt.pk)


def test_reconciliation_streams_and_verifies_referenced_templates_and_artifacts(
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stored_records(user_factory)
    chunk_sizes: list[int | None] = []
    original_chunks = File.chunks

    def tracked_chunks(self: File[bytes], chunk_size: int | None = None) -> Iterator[bytes]:
        chunk_sizes.append(chunk_size)
        yield from original_chunks(self, chunk_size=chunk_size)

    monkeypatch.setattr(File, "chunks", tracked_chunks)

    report = reconcile_private_files()

    assert report.status == "ok"
    assert report.counts["templates_checked"] == 1
    assert report.counts["artifacts_checked"] == 1
    assert report.counts["integrity_breaches"] == 0
    assert chunk_sizes == [64 * 1024, 64 * 1024]


@pytest.mark.parametrize(
    ("target", "change", "expected_category"),
    [
        ("template", "delete", "templates_missing"),
        ("template", "replace", "templates_modified"),
        ("artifact", "delete", "artifacts_missing"),
        ("artifact", "replace", "artifacts_modified"),
    ],
)
def test_reconciliation_detects_missing_and_modified_references(
    user_factory: object,
    target: str,
    change: str,
    expected_category: str,
) -> None:
    template, artifact = _stored_records(user_factory)
    key = template.storage_key if target == "template" else artifact.output_storage_key
    storage = storages["private"]
    storage.delete(key)
    if change == "replace":
        storage.save(key, ContentFile(b"tampered-private-content"))

    report = reconcile_private_files()

    assert report.status == "integrity_breach"
    assert report.counts[expected_category] == 1
    assert report.counts["integrity_breaches"] == 1


def test_check_command_returns_bounded_json_and_fails_on_integrity_breach(
    user_factory: object,
) -> None:
    template, _artifact = _stored_records(user_factory)
    storages["private"].delete(template.storage_key)
    stdout = io.StringIO()

    with pytest.raises(CommandError, match="integrity findings"):
        call_command("reconcile_private_files", "--check", stdout=stdout)

    output = stdout.getvalue()
    event = json.loads(output.splitlines()[0])
    assert event["event"] == "private_file_reconciliation_completed"
    assert event["status"] == "integrity_breach"
    assert event["severity"] == "error"
    assert re.fullmatch(r"[0-9a-f]{32}", event["correlation_id"])
    assert event["timestamp"].endswith("+00:00")
    assert event["counts"]["templates_missing"] == 1
    assert template.storage_key not in output
    assert template.original_filename not in output


def test_reconciliation_classifies_storage_errors_without_exposing_details(
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template, _artifact = _stored_records(user_factory)
    original_open = storages["private"].open

    def denied_open(name: str, mode: str = "rb") -> Any:
        if name == template.storage_key:
            raise PermissionError("synthetic-sensitive-path")
        return original_open(name, mode)

    monkeypatch.setattr(storages["private"], "open", denied_open)

    report = reconcile_private_files()

    assert report.status == "integrity_breach"
    assert report.counts["storage_errors"] == 1
    assert "synthetic-sensitive-path" not in json.dumps(report.as_event())


def test_reconciliation_does_not_hide_an_interrupted_scan(
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stored_records(user_factory)

    def interrupted_iterator(*args: object, **kwargs: object) -> Iterator[tuple[object, ...]]:
        raise KeyboardInterrupt
        yield ()

    monkeypatch.setattr(reconciliation, "_template_references", interrupted_iterator)

    with pytest.raises(KeyboardInterrupt):
        reconcile_private_files()


def test_reconciliation_reports_final_orphans_without_deleting_them(
    user_factory: object,
) -> None:
    _stored_records(user_factory)
    orphan_key = f"generated/{uuid4()}/{uuid4()}/{uuid4().hex}.docx"
    storage = storages["private"]
    storage.save(orphan_key, ContentFile(b"unreferenced-final-content"))

    report = reconcile_private_files()

    assert report.status == "integrity_breach"
    assert report.counts["orphaned_files"] == 1
    assert report.counts["integrity_breaches"] == 1
    assert storage.exists(orphan_key)
    assert orphan_key not in json.dumps(report.as_event())


def test_reconciliation_leaves_fresh_staging_files_alone(user_factory: object) -> None:
    template, _artifact = _stored_records(user_factory)
    staging_path = Path(storages["private"].path(template.storage_key)).parent
    fresh_stage = staging_path / ".immutable-stage-current.tmp"
    fresh_stage.write_bytes(b"in-progress")

    report = reconcile_private_files(cleanup_stale_staging=True)

    assert report.status == "ok"
    assert report.counts["staging_files"] == 1
    assert report.counts["stale_staging_files"] == 0
    assert report.counts["staging_files_removed"] == 0
    assert fresh_stage.exists()


def test_stale_staging_cleanup_is_explicit_narrow_and_idempotent(
    user_factory: object,
) -> None:
    template, _artifact = _stored_records(user_factory)
    staging_path = Path(storages["private"].path(template.storage_key)).parent
    stale_stage = staging_path / ".immutable-stage-abandoned.tmp"
    stale_stage.write_bytes(b"abandoned")
    stale_time = (timezone.now() - timedelta(days=2)).timestamp()
    os.utime(stale_stage, (stale_time, stale_time))

    read_only = reconcile_private_files()

    assert read_only.status == "integrity_breach"
    assert read_only.counts["stale_staging_files"] == 1
    assert read_only.counts["staging_files_removed"] == 0
    assert stale_stage.exists()

    cleaned = reconcile_private_files(cleanup_stale_staging=True)
    repeated = reconcile_private_files(cleanup_stale_staging=True)

    assert cleaned.status == "ok"
    assert cleaned.counts["stale_staging_files"] == 1
    assert cleaned.counts["staging_files_removed"] == 1
    assert not stale_stage.exists()
    assert repeated.status == "ok"
    assert repeated.counts["stale_staging_files"] == 0
    assert repeated.counts["staging_files_removed"] == 0


def test_cleanup_never_follows_or_removes_staging_symlinks(
    user_factory: object,
    tmp_path: Path,
) -> None:
    template, _artifact = _stored_records(user_factory)
    outside = tmp_path / "outside-private-root"
    outside.write_bytes(b"must-remain")
    staging_path = Path(storages["private"].path(template.storage_key)).parent
    unsafe_stage = staging_path / ".immutable-stage-unsafe.tmp"
    unsafe_stage.symlink_to(outside)

    report = reconcile_private_files(cleanup_stale_staging=True)

    assert report.status == "integrity_breach"
    assert report.counts["unsafe_entries"] == 1
    assert report.counts["staging_files_removed"] == 0
    assert unsafe_stage.is_symlink()
    assert outside.read_bytes() == b"must-remain"


def test_reconciliation_never_opens_a_referenced_symlink(
    user_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template, _artifact = _stored_records(user_factory)
    storage = storages["private"]
    template_path = Path(storage.path(template.storage_key))
    outside = tmp_path / "outside-referenced-content"
    outside.write_bytes(template_path.read_bytes())
    template_path.unlink()
    template_path.symlink_to(outside)
    original_open = storage.open
    opened_keys: list[str] = []

    def tracked_open(name: str, mode: str = "rb") -> Any:
        opened_keys.append(name)
        return original_open(name, mode)

    monkeypatch.setattr(storage, "open", tracked_open)

    report = reconcile_private_files()

    assert report.status == "integrity_breach"
    assert report.counts["unsafe_entries"] == 1
    assert template.storage_key not in opened_keys


def test_reconciliation_rejects_a_storage_outside_the_configured_private_root(
    tmp_path: Path,
) -> None:
    unexpected_storage = PrivateFileSystemStorage(location=tmp_path / "unexpected")

    with pytest.raises(PrivateStorageConfigurationError):
        reconcile_private_files(storage=unexpected_storage)


def test_cleanup_command_rejects_read_only_check_mode() -> None:
    with pytest.raises(CommandError, match="cannot be combined"):
        call_command("reconcile_private_files", "--check", "--cleanup-stale-staging")


def test_reconciliation_rejects_a_non_filesystem_storage() -> None:
    with pytest.raises(PrivateStorageConfigurationError):
        reconcile_private_files(storage=Storage())


def test_reconciliation_rejects_a_private_root_that_is_not_a_directory(
    settings: Any,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private-file"
    private_root.write_bytes(b"not-a-directory")
    settings.PRIVATE_STORAGE_ROOT = private_root
    storage = PrivateFileSystemStorage(location=private_root)

    with pytest.raises(PrivateStorageConfigurationError):
        reconcile_private_files(storage=storage)


def test_reconciliation_accepts_an_absent_empty_private_root() -> None:
    report = reconcile_private_files()

    assert report.status == "ok"
    assert report.counts["integrity_breaches"] == 0


def test_reconciliation_handles_a_reference_deleted_between_exists_and_open(
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template, _artifact = _stored_records(user_factory)
    storage = storages["private"]
    original_open = storage.open

    def racing_open(name: str, mode: str = "rb") -> Any:
        if name == template.storage_key:
            raise FileNotFoundError
        return original_open(name, mode)

    monkeypatch.setattr(storage, "open", racing_open)

    report = reconcile_private_files()

    assert report.counts["templates_missing"] == 1


def test_reconciliation_rejects_non_binary_storage_chunks(
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stored_records(user_factory)

    def text_chunks(self: File[bytes], chunk_size: int | None = None) -> Iterator[Any]:
        yield "not-binary"

    monkeypatch.setattr(File, "chunks", text_chunks)

    report = reconcile_private_files()

    assert report.counts["storage_errors"] == 2


def test_reconciliation_reports_special_files_as_unsafe(
    _isolated_private_storage: Path,
) -> None:
    generated_root = _isolated_private_storage / "generated"
    generated_root.mkdir(parents=True)
    os.mkfifo(generated_root / "unexpected-pipe")

    report = reconcile_private_files()

    assert report.counts["unsafe_entries"] == 1


def test_reconciliation_reports_inventory_permission_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_storage = cast(PrivateFileSystemStorage, storages["private"])
    Path(private_storage.location).mkdir(parents=True)

    def denied_scan(path: object) -> Any:
        raise PermissionError("synthetic-private-path")

    monkeypatch.setattr(os, "scandir", denied_scan)

    report = reconcile_private_files()

    assert report.counts["inventory_errors"] == 1
    assert "synthetic-private-path" not in json.dumps(report.as_event())


def test_cleanup_reports_an_unlink_failure_without_disclosing_it(
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template, _artifact = _stored_records(user_factory)
    staging_path = Path(storages["private"].path(template.storage_key)).parent
    stale_stage = staging_path / ".immutable-stage-locked.tmp"
    stale_stage.write_bytes(b"abandoned")
    stale_time = (timezone.now() - timedelta(days=2)).timestamp()
    os.utime(stale_stage, (stale_time, stale_time))
    original_unlink = Path.unlink

    def denied_unlink(path: Path, missing_ok: bool = False) -> None:
        if path == stale_stage:
            raise PermissionError("synthetic-private-path")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", denied_unlink)

    report = reconcile_private_files(cleanup_stale_staging=True)

    assert report.status == "integrity_breach"
    assert report.counts["cleanup_errors"] == 1
    assert "synthetic-private-path" not in json.dumps(report.as_event())


def test_cleanup_rechecks_staging_age_before_unlink(
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template, _artifact = _stored_records(user_factory)
    staging_path = Path(storages["private"].path(template.storage_key)).parent
    stale_stage = staging_path / ".immutable-stage-refreshed.tmp"
    stale_stage.write_bytes(b"active-again")
    stale_time = (timezone.now() - timedelta(days=2)).timestamp()
    os.utime(stale_stage, (stale_time, stale_time))
    original_lstat = Path.lstat

    def refreshed_lstat(path: Path) -> Any:
        if path == stale_stage:
            return SimpleNamespace(st_mode=path.stat().st_mode, st_mtime=time.time())
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", refreshed_lstat)

    report = reconcile_private_files(cleanup_stale_staging=True)

    assert report.counts["cleanup_errors"] == 1
    assert report.counts["staging_files_removed"] == 0
    assert stale_stage.exists()


def test_command_converts_private_root_configuration_failure_to_bounded_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_configuration(**kwargs: object) -> Any:
        raise PrivateStorageConfigurationError("bounded configuration failure")

    monkeypatch.setattr(
        reconciliation_command,
        "reconcile_private_files",
        invalid_configuration,
    )

    with pytest.raises(CommandError, match="bounded configuration failure"):
        call_command("reconcile_private_files")
