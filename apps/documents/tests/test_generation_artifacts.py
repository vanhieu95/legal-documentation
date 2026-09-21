from __future__ import annotations

import hashlib
import traceback
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile, File
from django.core.files.storage import Storage

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.cases.models import CaseRecord
from apps.core.storage import PrivateFileSystemStorage
from apps.documents import generation_artifacts as artifacts
from apps.documents.generation_artifacts import GenerationAttemptFailed, generate_artifact
from apps.documents.models import DocumentDraft, GeneratedDocument, TemplateVersion
from apps.documents.output_validation import InvalidRenderedDocument
from apps.documents.registry import document_registry
from apps.documents.storage_keys import (
    build_generated_display_filename,
    build_generated_storage_key,
    build_template_storage_key,
)
from apps.documents.tests.test_generation_rendering import _template_bytes
from apps.documents.tests.test_template_versions import template_values
from tests.factories import CaseRecordFactory

pytestmark = pytest.mark.django_db


def _prepared_attempt(
    user_factory: object,
    tmp_path: Path,
    *,
    template_version: str = "artifact-v1",
) -> tuple[User, DocumentDraft, GeneratedDocument, PrivateFileSystemStorage, bytes]:
    actor = user_factory(username=f"artifact-admin-{uuid4().hex[:8]}")  # type: ignore[operator]
    actor.groups.add(seed_administrator_permissions())
    case = cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))
    package = _template_bytes()
    storage = PrivateFileSystemStorage(location=tmp_path)
    template_key = build_template_storage_key("synthetic-platform-test", template_version)
    assert storage.save(template_key, ContentFile(package)) == template_key
    template = TemplateVersion.objects.create(
        **template_values(
            uploader=actor,
            version=template_version,
            storage_key=template_key,
            checksum_sha256=hashlib.sha256(package).hexdigest(),
            byte_size=len(package),
        )
    )
    draft = DocumentDraft.objects.create(
        case=case,
        type_key="synthetic-platform-test",
        schema_version="v1",
        payload={
            "title": "Giá trị văn bản",
            "notes": "Nội dung <&> an toàn",
            "participant_id": None,
        },
        state=DocumentDraft.State.READY,
        revision=1,
        created_by=actor,
        last_edited_by=actor,
    )
    attempt = GeneratedDocument.objects.create(
        case=case,
        type_key="synthetic-platform-test",
        template_version=template,
        schema_version="v1",
        source_draft_id=draft.pk,
        case_revision=case.revision,
        draft_revision=draft.revision,
        input_snapshot={"version": 1, "values": draft.payload},
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
    return actor, draft, attempt, storage, package


def _artifact_names(storage: Storage) -> list[str]:
    directories, _files = storage.listdir("generated") if storage.exists("generated") else ([], [])
    names: list[str] = []
    for case_directory in directories:
        attempt_directories, _ = storage.listdir(f"generated/{case_directory}")
        for attempt_directory in attempt_directories:
            _, files = storage.listdir(f"generated/{case_directory}/{attempt_directory}")
            names.extend(
                f"generated/{case_directory}/{attempt_directory}/{filename}" for filename in files
            )
    return names


def test_valid_output_is_verified_stored_privately_and_finalized_once(
    user_factory: object,
    tmp_path: Path,
) -> None:
    actor, draft, attempt, storage, _package = _prepared_attempt(user_factory, tmp_path)

    generated = generate_artifact(
        actor=actor,
        attempt_id=attempt.pk,
        correlation_id="artifact-success-test",
        storage=storage,
    )
    duplicate = generate_artifact(
        actor=actor,
        attempt_id=attempt.pk,
        correlation_id="artifact-duplicate-test",
        storage=storage,
    )

    assert generated.status == GeneratedDocument.Status.GENERATED
    assert duplicate.pk == generated.pk
    assert duplicate.output_storage_key == generated.output_storage_key
    assert generated.generated_at is not None
    assert generated.failed_at is None
    assert generated.output_filename.endswith(f"-{attempt.pk.hex[:8]}.docx")
    assert len(generated.output_filename) <= 150
    assert generated.output_storage_key.startswith(f"generated/{attempt.case_id}/{attempt.pk}/")
    assert storage.exists(generated.output_storage_key)
    with storage.open(generated.output_storage_key, "rb") as artifact:
        content = artifact.read()
    assert generated.output_size == len(content)
    assert generated.output_checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert _artifact_names(storage) == [generated.output_storage_key]
    assert Path(storage.path(generated.output_storage_key)).stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.rglob(".immutable-stage-*.tmp"))
    assert DocumentDraft.objects.get(pk=draft.pk).payload == draft.payload
    assert (
        AuditEvent.objects.filter(
            action=AuditAction.DOCUMENT_GENERATION_SUCCEEDED,
            target_id=str(attempt.pk),
        ).count()
        == 1
    )


@pytest.mark.parametrize(
    ("proposed", "expected_stem"),
    [
        ("../CON.docx", "template-CON"),
        ("CON.txt.docx", "template-CON.txt"),
        ("LPT1.any.docx", "template-LPT1.any"),
        ("folder\\unsafe/name?.docx", "name"),
        ("  ba\x00o cao .DOCX ", "bao cao"),
        ("Đề nghị.docx", "Đề nghị"),
    ],
)
def test_generated_display_filename_is_cross_platform_safe_and_unique(
    proposed: str,
    expected_stem: str,
) -> None:
    attempt_id = UUID("12345678-1234-5678-1234-567812345678")

    filename = build_generated_display_filename(proposed, attempt_id)

    assert filename == f"{expected_stem}-12345678.docx"
    assert len(filename) <= 150
    assert not set('/\\<>:"|?*\x00') & set(filename)


def test_generated_key_is_server_owned_unique_and_identity_scoped() -> None:
    case_id = uuid4()
    attempt_id = uuid4()

    first = build_generated_storage_key(case_id, attempt_id)
    second = build_generated_storage_key(case_id, attempt_id)

    assert first != second
    assert first.startswith(f"generated/{case_id}/{attempt_id}/")
    assert first.endswith(".docx")


def test_atomic_private_placement_never_overwrites_an_existing_key(tmp_path: Path) -> None:
    storage = PrivateFileSystemStorage(location=tmp_path)
    key = build_generated_storage_key(uuid4(), uuid4())
    storage.save_immutable(key, ContentFile(b"first"))

    with pytest.raises(FileExistsError):
        storage.save_immutable(key, ContentFile(b"second"))

    with storage.open(key, "rb") as stored:
        assert stored.read() == b"first"
    assert not list(tmp_path.rglob(".immutable-stage-*.tmp"))


class _WriteThenFailStorage(PrivateFileSystemStorage):
    def save_immutable(
        self,
        name: str,
        content: File[bytes],
    ) -> str:
        super().save_immutable(name, content)
        raise OSError("private storage path and payload")


class _CorruptingStorage(PrivateFileSystemStorage):
    def save_immutable(
        self,
        name: str,
        content: File[bytes],
    ) -> str:
        if name.startswith("generated/"):
            content = ContentFile(b"corrupt artifact")
        return super().save_immutable(name, content)


class _RenamingStorage(PrivateFileSystemStorage):
    def save_immutable(self, name: str, content: File[bytes]) -> str:
        changed_name = name.replace(name.rsplit("/", 1)[-1], f"{uuid4().hex}.docx")
        return super().save_immutable(changed_name, content)


class _UnreadableArtifactStorage(PrivateFileSystemStorage):
    def open(self, name: str, mode: str = "rb") -> File[Any]:
        if name.startswith("generated/"):
            raise OSError("private artifact path")
        return super().open(name, mode)


class _UnsafeReturnStorage(PrivateFileSystemStorage):
    def save_immutable(self, name: str, content: File[bytes]) -> str:
        super().save_immutable(name, content)
        return "outside-the-attempt.docx"


@pytest.mark.parametrize(
    ("failure_point", "expected_category"),
    [
        ("mapper", GeneratedDocument.FailureCategory.CONTEXT_MISSING),
        ("render", GeneratedDocument.FailureCategory.RENDER_ERROR),
        ("validation", GeneratedDocument.FailureCategory.INTEGRITY_ERROR),
        ("storage", GeneratedDocument.FailureCategory.STORAGE_ERROR),
        ("finalization", GeneratedDocument.FailureCategory.INTEGRITY_ERROR),
    ],
)
def test_every_pipeline_failure_persists_safe_state_and_removes_partial_output(
    failure_point: str,
    expected_category: str,
    user_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, draft, attempt, original_storage, _package = _prepared_attempt(user_factory, tmp_path)
    storage: PrivateFileSystemStorage = original_storage
    sensitive_value = str(draft.payload["notes"])
    correlation_id = sensitive_value

    if failure_point == "mapper":
        registration = replace(
            document_registry.get("synthetic-platform-test"),
            context_mapper=lambda _values: {},
        )
        monkeypatch.setattr(
            "apps.documents.generation_rendering.document_registry",
            type("Registry", (), {"get": staticmethod(lambda _key: registration)})(),
        )
    elif failure_point == "render":
        monkeypatch.setattr(
            "apps.documents.generation_rendering.DocxTemplate.render",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(sensitive_value)),
        )
    elif failure_point == "validation":
        monkeypatch.setattr(
            "apps.documents.generation_rendering.inspect_rendered_docx",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                InvalidRenderedDocument(sensitive_value)
            ),
        )
    elif failure_point == "storage":
        storage = _WriteThenFailStorage(location=tmp_path)
    else:
        monkeypatch.setattr(
            "apps.documents.generation_artifacts._finalize_success",
            lambda **_kwargs: (_ for _ in ()).throw(OSError(sensitive_value)),
        )

    with pytest.raises(GenerationAttemptFailed) as error:
        generate_artifact(
            actor=actor,
            attempt_id=attempt.pk,
            correlation_id=correlation_id,
            storage=storage,
        )

    failed = GeneratedDocument.objects.get(pk=attempt.pk)
    assert failed.status == GeneratedDocument.Status.FAILED
    assert failed.failure_category == expected_category
    assert failed.failed_at is not None
    assert failed.failure_correlation_id
    assert failed.failure_correlation_id != sensitive_value
    assert not failed.output_storage_key
    assert _artifact_names(original_storage) == []
    assert DocumentDraft.objects.get(pk=draft.pk).payload == draft.payload
    assert sensitive_value not in str(error.value)
    assert sensitive_value not in "".join(traceback.format_exception(error.value))
    assert error.value.__cause__ is None
    event = AuditEvent.objects.get(
        action=AuditAction.DOCUMENT_GENERATION_FAILED,
        target_id=str(attempt.pk),
    )
    assert event.outcome == "failure"
    assert event.metadata == {
        "failure_category": expected_category,
        "schema_version": "v1",
        "template_version": "artifact-v1",
        "type_key": "synthetic-platform-test",
    }
    assert sensitive_value not in str(event.metadata)


def test_post_write_checksum_mismatch_is_failed_and_cleaned(
    user_factory: object,
    tmp_path: Path,
) -> None:
    actor, _draft, attempt, _storage, _package = _prepared_attempt(user_factory, tmp_path)
    storage = _CorruptingStorage(location=tmp_path)

    with pytest.raises(GenerationAttemptFailed):
        generate_artifact(
            actor=actor,
            attempt_id=attempt.pk,
            correlation_id="artifact-integrity-test",
            storage=storage,
        )

    attempt.refresh_from_db()
    assert attempt.failure_category == GeneratedDocument.FailureCategory.INTEGRITY_ERROR
    assert _artifact_names(storage) == []


@pytest.mark.parametrize(
    ("storage_class", "expected_category"),
    [
        (_RenamingStorage, GeneratedDocument.FailureCategory.STORAGE_ERROR),
        (_UnreadableArtifactStorage, GeneratedDocument.FailureCategory.STORAGE_ERROR),
        (_UnsafeReturnStorage, GeneratedDocument.FailureCategory.STORAGE_ERROR),
    ],
)
def test_changed_storage_key_or_unreadable_artifact_is_failed_and_cleaned(
    storage_class: type[PrivateFileSystemStorage],
    expected_category: str,
    user_factory: object,
    tmp_path: Path,
) -> None:
    actor, _draft, attempt, _storage, _package = _prepared_attempt(user_factory, tmp_path)
    storage = storage_class(location=tmp_path)

    with pytest.raises(GenerationAttemptFailed):
        generate_artifact(
            actor=actor,
            attempt_id=attempt.pk,
            correlation_id="artifact-storage-contract-test",
            storage=storage,
        )

    attempt.refresh_from_db()
    assert attempt.failure_category == expected_category
    assert _artifact_names(storage) == []


@pytest.mark.parametrize(
    ("mutation", "expected_category"),
    [
        ("missing", GeneratedDocument.FailureCategory.STORAGE_ERROR),
        ("truncated", GeneratedDocument.FailureCategory.INTEGRITY_ERROR),
    ],
)
def test_missing_or_truncated_reserved_template_fails_before_rendering(
    mutation: str,
    expected_category: str,
    user_factory: object,
    tmp_path: Path,
) -> None:
    actor, _draft, attempt, storage, package = _prepared_attempt(user_factory, tmp_path)
    template_path = Path(storage.path(attempt.template_version.storage_key))
    if mutation == "missing":
        template_path.unlink()
    else:
        template_path.write_bytes(package[:-1])

    with pytest.raises(GenerationAttemptFailed):
        generate_artifact(
            actor=actor,
            attempt_id=attempt.pk,
            correlation_id="artifact-template-storage-test",
            storage=storage,
        )

    attempt.refresh_from_db()
    assert attempt.failure_category == expected_category


def test_filename_builder_output_is_sanitized_and_builder_failure_is_bounded(
    user_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, _draft, attempt, storage, _package = _prepared_attempt(
        user_factory,
        tmp_path,
        template_version="artifact-v2",
    )
    registration = replace(
        document_registry.get("synthetic-platform-test"),
        filename_builder=lambda _values: "../CON?.docx",
    )
    monkeypatch.setattr(
        artifacts,
        "document_registry",
        SimpleNamespace(get=lambda _key: registration),
    )

    generated = generate_artifact(
        actor=actor,
        attempt_id=attempt.pk,
        correlation_id="artifact-safe-name-test",
        storage=storage,
    )

    assert generated.output_filename == f"template-CON-{attempt.pk.hex[:8]}.docx"

    actor, _draft, attempt, storage, _package = _prepared_attempt(user_factory, tmp_path)
    failing_registration = replace(
        registration,
        filename_builder=lambda _values: (_ for _ in ()).throw(ValueError("private value")),
    )
    monkeypatch.setattr(
        artifacts,
        "document_registry",
        SimpleNamespace(get=lambda _key: failing_registration),
    )
    with pytest.raises(GenerationAttemptFailed) as error:
        generate_artifact(
            actor=actor,
            attempt_id=attempt.pk,
            correlation_id="artifact-name-failure-test",
            storage=storage,
        )
    attempt.refresh_from_db()
    assert attempt.failure_category == GeneratedDocument.FailureCategory.RENDER_ERROR
    assert "private value" not in str(error.value)


def test_concurrent_success_keeps_winning_artifact_and_cleans_losing_output(
    user_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, _draft, attempt, storage, _package = _prepared_attempt(user_factory, tmp_path)

    def finalize_elsewhere(**kwargs: object) -> GeneratedDocument:
        rendered = cast(artifacts.RenderedDocument, kwargs["rendered"])
        winning_key = build_generated_storage_key(attempt.case_id, attempt.pk)
        storage.save_immutable(winning_key, ContentFile(rendered.content))
        artifacts.models.QuerySet.update(
            GeneratedDocument.objects.filter(pk=attempt.pk),
            status=GeneratedDocument.Status.GENERATED,
            generated_at=artifacts.timezone.now(),
            output_storage_key=winning_key,
            output_filename="winner.docx",
            output_size=rendered.byte_size,
            output_checksum_sha256=rendered.checksum_sha256,
        )
        return GeneratedDocument.objects.select_related("template_version").get(pk=attempt.pk)

    monkeypatch.setattr(artifacts, "_finalize_success", finalize_elsewhere)

    generated = generate_artifact(
        actor=actor,
        attempt_id=attempt.pk,
        correlation_id="artifact-concurrent-success",
        storage=storage,
    )

    assert _artifact_names(storage) == [generated.output_storage_key]
    assert generated.output_filename == "winner.docx"


def test_concurrent_failure_is_not_rewritten_and_losing_output_is_cleaned(
    user_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, _draft, attempt, storage, _package = _prepared_attempt(user_factory, tmp_path)

    def fail_elsewhere(**_kwargs: object) -> GeneratedDocument:
        artifacts.models.QuerySet.update(
            GeneratedDocument.objects.filter(pk=attempt.pk),
            status=GeneratedDocument.Status.FAILED,
            failed_at=artifacts.timezone.now(),
            failure_category=GeneratedDocument.FailureCategory.INTEGRITY_ERROR,
            failure_correlation_id="concurrent-failure",
        )
        return GeneratedDocument.objects.select_related("template_version").get(pk=attempt.pk)

    monkeypatch.setattr(artifacts, "_finalize_success", fail_elsewhere)

    with pytest.raises(GenerationAttemptFailed):
        generate_artifact(
            actor=actor,
            attempt_id=attempt.pk,
            correlation_id="artifact-concurrent-failure",
            storage=storage,
        )

    assert _artifact_names(storage) == []
    attempt.refresh_from_db()
    assert attempt.failure_correlation_id == "concurrent-failure"


def test_internal_terminal_and_compare_and_swap_paths_are_bounded(
    user_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, _draft, attempt, storage, _package = _prepared_attempt(user_factory, tmp_path)
    generated = generate_artifact(
        actor=actor,
        attempt_id=attempt.pk,
        correlation_id="artifact-terminal-test",
        storage=storage,
    )
    terminal = artifacts._finalize_success(
        actor=actor,
        attempt_id=attempt.pk,
        storage_key=generated.output_storage_key,
        filename=generated.output_filename,
        rendered=cast(
            artifacts.RenderedDocument,
            SimpleNamespace(
                byte_size=generated.output_size,
                checksum_sha256=generated.output_checksum_sha256,
            ),
        ),
        correlation_id="artifact-terminal-test",
    )
    assert terminal.status == GeneratedDocument.Status.GENERATED

    actor, _draft, attempt, _storage, _package = _prepared_attempt(
        user_factory,
        tmp_path,
        template_version="artifact-cas-v1",
    )
    monkeypatch.setattr(artifacts.models.QuerySet, "update", lambda *_args, **_kwargs: 0)
    with pytest.raises(artifacts.GenerationFailurePersistenceError):
        artifacts._mark_failed(
            actor=actor,
            attempt_id=attempt.pk,
            category=GeneratedDocument.FailureCategory.INTEGRITY_ERROR,
            correlation_id="artifact-cas-failure",
        )


def test_cleanup_guards_paths_and_swallows_backend_cleanup_error(
    user_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _actor, _draft, attempt, storage, _package = _prepared_attempt(user_factory, tmp_path)
    safe_key = build_generated_storage_key(attempt.case_id, attempt.pk)
    storage.save_immutable(safe_key, ContentFile(b"partial"))
    monkeypatch.setattr(storage, "exists", lambda _key: (_ for _ in ()).throw(OSError()))

    artifacts._cleanup(storage, attempt, {"templates/not-owned.docx", safe_key})

    assert Path(storage.path(safe_key)).exists()


def test_filename_context_failure_and_nested_list_correlation_are_safe(
    user_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _actor, _draft, attempt, _storage, _package = _prepared_attempt(user_factory, tmp_path)
    monkeypatch.setattr(
        artifacts,
        "document_registry",
        SimpleNamespace(get=lambda _key: (_ for _ in ()).throw(artifacts.UnknownDocumentTypeKey())),
    )
    with pytest.raises(artifacts._ArtifactPipelineError) as error:
        artifacts._display_filename(attempt)
    assert error.value.category == GeneratedDocument.FailureCategory.CONTEXT_MISSING

    attempt.input_snapshot = {"version": 1, "values": {"items": ["nested-correlation"]}}
    assert artifacts._safe_correlation_id("nested-correlation", attempt) != "nested-correlation"
    attempt.input_snapshot = {"version": 1, "values": {"title": "private-case-value"}}
    embedded = "prefix-private-case-value-suffix"
    assert artifacts._safe_correlation_id(embedded, attempt) != embedded


def test_invalid_private_backend_is_a_durable_storage_failure(
    user_factory: object,
    tmp_path: Path,
) -> None:
    actor, _draft, attempt, _storage, _package = _prepared_attempt(user_factory, tmp_path)

    with pytest.raises(GenerationAttemptFailed):
        generate_artifact(
            actor=actor,
            attempt_id=attempt.pk,
            correlation_id="artifact-backend-contract",
            storage=cast(PrivateFileSystemStorage, object()),
        )

    attempt.refresh_from_db()
    assert attempt.failure_category == GeneratedDocument.FailureCategory.STORAGE_ERROR


def test_concurrent_success_wins_while_failure_is_being_recorded(
    user_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, _draft, attempt, storage, package = _prepared_attempt(user_factory, tmp_path)
    Path(storage.path(attempt.template_version.storage_key)).unlink()

    def succeed_elsewhere(**_kwargs: object) -> GeneratedDocument:
        winning_key = build_generated_storage_key(attempt.case_id, attempt.pk)
        storage.save_immutable(winning_key, ContentFile(package))
        artifacts.models.QuerySet.update(
            GeneratedDocument.objects.filter(pk=attempt.pk),
            status=GeneratedDocument.Status.GENERATED,
            generated_at=artifacts.timezone.now(),
            output_storage_key=winning_key,
            output_filename="winner.docx",
            output_size=len(package),
            output_checksum_sha256=hashlib.sha256(package).hexdigest(),
        )
        return GeneratedDocument.objects.select_related("template_version").get(pk=attempt.pk)

    monkeypatch.setattr(artifacts, "_mark_failed", succeed_elsewhere)

    generated = generate_artifact(
        actor=actor,
        attempt_id=attempt.pk,
        correlation_id="artifact-racing-failure",
        storage=storage,
    )

    assert generated.status == GeneratedDocument.Status.GENERATED


def test_failed_attempt_is_never_rewritten_and_retry_uses_a_new_row(
    user_factory: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, draft, attempt, storage, package = _prepared_attempt(user_factory, tmp_path)
    monkeypatch.setattr(
        "apps.documents.generation_rendering.DocxTemplate.render",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("render failure")),
    )
    with pytest.raises(GenerationAttemptFailed):
        generate_artifact(
            actor=actor,
            attempt_id=attempt.pk,
            correlation_id="artifact-first-failure",
            storage=storage,
        )
    monkeypatch.undo()

    with pytest.raises(GenerationAttemptFailed):
        generate_artifact(
            actor=actor,
            attempt_id=attempt.pk,
            correlation_id="artifact-no-rewrite",
            storage=storage,
        )
    retry = GeneratedDocument.objects.create(
        case=attempt.case,
        type_key=attempt.type_key,
        template_version=attempt.template_version,
        schema_version=attempt.schema_version,
        source_draft_id=draft.pk,
        case_revision=attempt.case_revision,
        draft_revision=draft.revision,
        input_snapshot=attempt.input_snapshot,
        resolved_values_snapshot=attempt.resolved_values_snapshot,
        override_snapshot=attempt.override_snapshot,
        template_snapshot=attempt.template_snapshot,
        actor=actor,
        idempotency_key_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
    )
    assert storage.exists(attempt.template_version.storage_key)
    assert hashlib.sha256(package).hexdigest() == attempt.template_version.checksum_sha256

    generated = generate_artifact(
        actor=actor,
        attempt_id=retry.pk,
        correlation_id="artifact-retry-success",
        storage=storage,
    )

    attempt.refresh_from_db()
    assert attempt.status == GeneratedDocument.Status.FAILED
    assert generated.status == GeneratedDocument.Status.GENERATED
    assert generated.pk != attempt.pk


def test_other_actor_cannot_finalize_reserved_attempt(
    user_factory: object,
    tmp_path: Path,
) -> None:
    actor, _draft, attempt, storage, _package = _prepared_attempt(user_factory, tmp_path)
    other = user_factory(username=f"other-admin-{uuid4().hex[:8]}")  # type: ignore[operator]
    other.groups.add(seed_administrator_permissions())

    with pytest.raises(PermissionDenied):
        generate_artifact(
            actor=other,
            attempt_id=attempt.pk,
            correlation_id="artifact-denied-test",
            storage=storage,
        )

    attempt.refresh_from_db()
    assert attempt.status == GeneratedDocument.Status.GENERATING
    assert _artifact_names(storage) == []
