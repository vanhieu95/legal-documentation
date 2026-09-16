from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import NoReturn
from uuid import UUID

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, storages
from django.db import models, transaction
from django.utils import timezone

from apps.accounts.policies import ApplicationPermission, service_permission_required
from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.recorder import AuditTarget, record_audit_event
from apps.core.correlation import generate_correlation_id, normalize_correlation_id
from apps.core.storage import PrivateFileSystemStorage
from apps.documents.generation_rendering import (
    GenerationRenderError,
    RenderedDocument,
    generation_snapshot_values,
    render_reserved_generation,
)
from apps.documents.models import GeneratedDocument
from apps.documents.registry import UnknownDocumentTypeKey, document_registry
from apps.documents.storage_keys import (
    build_generated_display_filename,
    build_generated_storage_key,
)

_GENERATED_KEY = re.compile(r"^generated/[0-9a-f-]{36}/[0-9a-f-]{36}/[0-9a-f]{32}\.docx$")


class GenerationAttemptFailed(RuntimeError):
    """A bounded recoverable outcome for an attempt that durably entered failed state."""

    def __init__(self, attempt_id: UUID, category: str) -> None:
        super().__init__("The document generation attempt failed safely.")
        self.attempt_id = attempt_id
        self.category = category


class GenerationFailurePersistenceError(RuntimeError):
    """Failure state could not be made durable and needs operational recovery."""


class _ArtifactPipelineError(Exception):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


def _owned_attempt(*, actor: User, attempt_id: UUID) -> GeneratedDocument:
    try:
        return GeneratedDocument.objects.select_related("template_version").get(
            pk=attempt_id,
            actor=actor,
        )
    except GeneratedDocument.DoesNotExist:
        raise PermissionDenied from None


def _read_template(attempt: GeneratedDocument, storage: Storage) -> bytes:
    try:
        with storage.open(attempt.template_version.storage_key, "rb") as source:
            content = source.read(attempt.template_version.byte_size + 1)
    except Exception:
        raise _ArtifactPipelineError(GeneratedDocument.FailureCategory.STORAGE_ERROR) from None
    if not isinstance(content, bytes) or len(content) != attempt.template_version.byte_size:
        raise _ArtifactPipelineError(GeneratedDocument.FailureCategory.INTEGRITY_ERROR)
    return content


def _display_filename(attempt: GeneratedDocument) -> str:
    try:
        registration = document_registry.get(attempt.type_key)
        proposed = registration.filename_builder(generation_snapshot_values(attempt))
        return build_generated_display_filename(proposed, attempt.pk)
    except (GenerationRenderError, UnknownDocumentTypeKey):
        raise _ArtifactPipelineError(GeneratedDocument.FailureCategory.CONTEXT_MISSING) from None
    except Exception:
        raise _ArtifactPipelineError(GeneratedDocument.FailureCategory.RENDER_ERROR) from None


def _safe_cleanup_key(attempt: GeneratedDocument, key: str) -> bool:
    prefix = f"generated/{attempt.case_id}/{attempt.pk}/"
    return key.startswith(prefix) and _GENERATED_KEY.fullmatch(key) is not None


def _cleanup(storage: Storage, attempt: GeneratedDocument, keys: set[str]) -> None:
    for key in keys:
        if not _safe_cleanup_key(attempt, key):
            continue
        try:
            if storage.exists(key):
                storage.delete(key)
        except Exception:
            continue


def _store_and_verify(
    *,
    attempt: GeneratedDocument,
    rendered: RenderedDocument,
    storage: PrivateFileSystemStorage,
    cleanup_keys: set[str],
) -> str:
    storage_key = build_generated_storage_key(attempt.case_id, attempt.pk)
    cleanup_keys.add(storage_key)
    try:
        saved_key = storage.save_immutable(storage_key, ContentFile(rendered.content))
    except Exception:
        raise _ArtifactPipelineError(GeneratedDocument.FailureCategory.STORAGE_ERROR) from None
    if _safe_cleanup_key(attempt, saved_key):
        cleanup_keys.add(saved_key)
    if saved_key != storage_key:
        raise _ArtifactPipelineError(GeneratedDocument.FailureCategory.STORAGE_ERROR)
    try:
        with storage.open(saved_key, "rb") as stored:
            stored_content = stored.read(rendered.byte_size + 1)
    except Exception:
        raise _ArtifactPipelineError(GeneratedDocument.FailureCategory.STORAGE_ERROR) from None
    if (
        not isinstance(stored_content, bytes)
        or len(stored_content) != rendered.byte_size
        or hashlib.sha256(stored_content).hexdigest() != rendered.checksum_sha256
    ):
        raise _ArtifactPipelineError(GeneratedDocument.FailureCategory.INTEGRITY_ERROR)
    return saved_key


def _audit(
    *,
    action: AuditAction,
    outcome: AuditOutcome,
    attempt: GeneratedDocument,
    correlation_id: str,
    changed_fields: tuple[str, ...],
    failure_category: str = "",
) -> None:
    metadata: dict[str, object] = {
        "type_key": attempt.type_key,
        "schema_version": attempt.schema_version,
        "template_version": attempt.template_version.version,
    }
    if failure_category:
        metadata["failure_category"] = failure_category
    record_audit_event(
        action=action,
        outcome=outcome,
        actor=attempt.actor,
        target=AuditTarget(type=AuditTargetType.GENERATED_DOCUMENT, id=str(attempt.pk)),
        correlation_id=correlation_id,
        changed_fields=changed_fields,
        metadata=metadata,
    )


def _finalize_success(
    *,
    actor: User,
    attempt_id: UUID,
    storage_key: str,
    filename: str,
    rendered: RenderedDocument,
    correlation_id: str,
) -> GeneratedDocument:
    with transaction.atomic():
        locked = (
            GeneratedDocument.objects.select_related("template_version")
            .select_for_update()
            .get(
                pk=attempt_id,
                actor=actor,
            )
        )
        if locked.status != GeneratedDocument.Status.GENERATING:
            return locked
        generated_at = timezone.now()
        updated = models.QuerySet.update(
            GeneratedDocument.objects.filter(
                pk=locked.pk,
                status=GeneratedDocument.Status.GENERATING,
            ),
            status=GeneratedDocument.Status.GENERATED,
            generated_at=generated_at,
            output_storage_key=storage_key,
            output_filename=filename,
            output_size=rendered.byte_size,
            output_checksum_sha256=rendered.checksum_sha256,
        )
        if updated != 1:
            raise _ArtifactPipelineError(GeneratedDocument.FailureCategory.INTEGRITY_ERROR)
        locked.status = GeneratedDocument.Status.GENERATED
        locked.generated_at = generated_at
        locked.output_storage_key = storage_key
        locked.output_filename = filename
        locked.output_size = rendered.byte_size
        locked.output_checksum_sha256 = rendered.checksum_sha256
        _audit(
            action=AuditAction.DOCUMENT_GENERATION_SUCCEEDED,
            outcome=AuditOutcome.SUCCESS,
            attempt=locked,
            correlation_id=correlation_id,
            changed_fields=(
                "status",
                "generated_at",
                "output_storage_key",
                "output_filename",
                "output_size",
                "output_checksum_sha256",
            ),
        )
        return locked


def _contains_value(value: object, candidate: str) -> bool:
    if isinstance(value, str):
        return bool(value) and (value in candidate or candidate in value)
    if isinstance(value, Mapping):
        return any(_contains_value(nested, candidate) for nested in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_value(nested, candidate) for nested in value)
    return False


def _safe_correlation_id(candidate: str, attempt: GeneratedDocument) -> str:
    normalized = normalize_correlation_id(candidate)
    snapshots = (
        attempt.input_snapshot,
        attempt.resolved_values_snapshot,
        attempt.override_snapshot,
        attempt.template_snapshot,
    )
    if normalized is None or any(_contains_value(value, normalized) for value in snapshots):
        return generate_correlation_id()
    return normalized


def _mark_failed(
    *,
    actor: User,
    attempt_id: UUID,
    category: str,
    correlation_id: str,
) -> GeneratedDocument:
    try:
        with transaction.atomic():
            locked = (
                GeneratedDocument.objects.select_related("template_version")
                .select_for_update()
                .get(pk=attempt_id, actor=actor)
            )
            if locked.status != GeneratedDocument.Status.GENERATING:
                return locked
            failed_at = timezone.now()
            updated = models.QuerySet.update(
                GeneratedDocument.objects.filter(
                    pk=locked.pk,
                    status=GeneratedDocument.Status.GENERATING,
                ),
                status=GeneratedDocument.Status.FAILED,
                failed_at=failed_at,
                failure_category=category,
                failure_correlation_id=correlation_id,
            )
            if updated != 1:
                raise GenerationFailurePersistenceError(
                    "The generation failure could not be persisted safely."
                )
            locked.status = GeneratedDocument.Status.FAILED
            locked.failed_at = failed_at
            locked.failure_category = category
            locked.failure_correlation_id = correlation_id
            _audit(
                action=AuditAction.DOCUMENT_GENERATION_FAILED,
                outcome=AuditOutcome.FAILURE,
                attempt=locked,
                correlation_id=correlation_id,
                changed_fields=(
                    "status",
                    "failed_at",
                    "failure_category",
                    "failure_correlation_id",
                ),
                failure_category=category,
            )
            return locked
    except GenerationFailurePersistenceError:
        raise
    except Exception:
        raise GenerationFailurePersistenceError(
            "The generation failure could not be persisted safely."
        ) from None


def _raise_existing_failure(attempt: GeneratedDocument) -> NoReturn:
    raise GenerationAttemptFailed(attempt.pk, attempt.failure_category)


@service_permission_required(ApplicationPermission.GENERATE_DOCUMENTS)
def generate_artifact(
    *,
    actor: User,
    attempt_id: UUID,
    correlation_id: str,
    storage: PrivateFileSystemStorage | None = None,
) -> GeneratedDocument:
    """Render, verify, privately place, and finalize one reserved immutable attempt."""
    attempt = _owned_attempt(actor=actor, attempt_id=attempt_id)
    if attempt.status == GeneratedDocument.Status.GENERATED:
        return attempt
    if attempt.status == GeneratedDocument.Status.FAILED:
        _raise_existing_failure(attempt)

    configured_storage = storages["private"] if storage is None else storage
    safe_correlation_id = _safe_correlation_id(correlation_id, attempt)
    if not isinstance(configured_storage, PrivateFileSystemStorage):
        failed = _mark_failed(
            actor=actor,
            attempt_id=attempt.pk,
            category=GeneratedDocument.FailureCategory.STORAGE_ERROR,
            correlation_id=safe_correlation_id,
        )
        raise GenerationAttemptFailed(failed.pk, failed.failure_category)
    private_storage = configured_storage
    cleanup_keys: set[str] = set()
    try:
        template_bytes = _read_template(attempt, private_storage)
        rendered = render_reserved_generation(attempt=attempt, template_bytes=template_bytes)
        filename = _display_filename(attempt)
        storage_key = _store_and_verify(
            attempt=attempt,
            rendered=rendered,
            storage=private_storage,
            cleanup_keys=cleanup_keys,
        )
        finalized = _finalize_success(
            actor=actor,
            attempt_id=attempt.pk,
            storage_key=storage_key,
            filename=filename,
            rendered=rendered,
            correlation_id=safe_correlation_id,
        )
        if finalized.status == GeneratedDocument.Status.GENERATED:
            if finalized.output_storage_key != storage_key:
                _cleanup(private_storage, attempt, cleanup_keys)
            return finalized
        raise _ArtifactPipelineError(finalized.failure_category)
    except GenerationRenderError as error:
        category = error.category.value
    except _ArtifactPipelineError as error:
        category = error.category
    except Exception:
        category = GeneratedDocument.FailureCategory.INTEGRITY_ERROR

    _cleanup(private_storage, attempt, cleanup_keys)
    failed = _mark_failed(
        actor=actor,
        attempt_id=attempt.pk,
        category=category,
        correlation_id=safe_correlation_id,
    )
    if failed.status == GeneratedDocument.Status.GENERATED:
        return failed
    raise GenerationAttemptFailed(failed.pk, failed.failure_category)
