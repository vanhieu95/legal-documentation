from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import quote
from uuid import UUID

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.files import File
from django.core.files.storage import Storage, storages

from apps.accounts.policies import ApplicationPermission, application_access_policy
from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.recorder import AuditTarget, record_audit_event
from apps.cases.models import CaseRecord
from apps.cases.policies import case_object_policy
from apps.documents.models import GeneratedDocument

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_ASCII_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")


class GeneratedDocumentDownloadNotFound(Exception):
    """The requested artifact is absent from the actor's authorized generated records."""


class GeneratedDocumentDownloadUnavailable(Exception):
    """The canonical artifact is missing or no longer matches its immutable metadata."""


@dataclass(frozen=True, slots=True)
class GeneratedDocumentDownload:
    attempt: GeneratedDocument
    source: File[bytes]


def build_content_disposition(filename: str) -> str:
    """Build an attachment value with a conservative fallback and RFC 5987 filename."""
    transliterated = unicodedata.normalize("NFKD", filename.replace("Đ", "D").replace("đ", "d"))
    ascii_name = transliterated.encode("ascii", "ignore").decode("ascii")
    ascii_name = _ASCII_FILENAME_UNSAFE.sub("_", ascii_name).strip(" .") or "document.docx"
    ascii_name = ascii_name.replace('"', "_").replace("\\", "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


def record_anonymous_download_denial(*, attempt_id: UUID, correlation_id: str) -> None:
    record_audit_event(
        action=AuditAction.DOCUMENT_DOWNLOADED,
        outcome=AuditOutcome.DENIED,
        target=AuditTarget(type=AuditTargetType.GENERATED_DOCUMENT, id=str(attempt_id)),
        correlation_id=correlation_id,
        is_system_actor=True,
    )


def _record_download(*, actor: User, attempt_id: UUID, outcome: str, correlation_id: str) -> None:
    record_audit_event(
        action=AuditAction.DOCUMENT_DOWNLOADED,
        outcome=outcome,
        target=AuditTarget(type=AuditTargetType.GENERATED_DOCUMENT, id=str(attempt_id)),
        correlation_id=correlation_id,
        actor=actor,
    )


def open_generated_document_download(
    *,
    actor: User,
    attempt_id: UUID,
    correlation_id: str,
    storage: Storage | None = None,
) -> GeneratedDocumentDownload:
    """Authorize, integrity-check, audit, and open the canonical stored artifact."""
    if not application_access_policy.has_permission(
        actor, ApplicationPermission.DOWNLOAD_DOCUMENTS
    ):
        _record_download(
            actor=actor,
            attempt_id=attempt_id,
            outcome=AuditOutcome.DENIED,
            correlation_id=correlation_id,
        )
        raise PermissionDenied

    accessible_cases = case_object_policy.scope_queryset(actor, CaseRecord.objects.all())
    try:
        attempt = GeneratedDocument.objects.get(
            pk=attempt_id,
            case__in=accessible_cases,
            status=GeneratedDocument.Status.GENERATED,
        )
    except GeneratedDocument.DoesNotExist:
        _record_download(
            actor=actor,
            attempt_id=attempt_id,
            outcome=AuditOutcome.DENIED,
            correlation_id=correlation_id,
        )
        raise GeneratedDocumentDownloadNotFound from None

    private_storage = storage or storages["private"]
    source: File[bytes] | None = None
    try:
        source = private_storage.open(attempt.output_storage_key, "rb")
        digest = hashlib.sha256()
        byte_size = 0
        for chunk in source.chunks():
            if not isinstance(chunk, bytes):
                raise TypeError("Private artifact storage returned non-binary content.")
            digest.update(chunk)
            byte_size += len(chunk)
        source.seek(0)
    except Exception:
        if source is not None:
            source.close()
        _record_download(
            actor=actor,
            attempt_id=attempt_id,
            outcome=AuditOutcome.FAILURE,
            correlation_id=correlation_id,
        )
        raise GeneratedDocumentDownloadUnavailable from None

    assert source is not None
    if byte_size != attempt.output_size or not hmac.compare_digest(
        digest.hexdigest(), attempt.output_checksum_sha256
    ):
        source.close()
        _record_download(
            actor=actor,
            attempt_id=attempt_id,
            outcome=AuditOutcome.FAILURE,
            correlation_id=correlation_id,
        )
        raise GeneratedDocumentDownloadUnavailable

    try:
        _record_download(
            actor=actor,
            attempt_id=attempt_id,
            outcome=AuditOutcome.SUCCESS,
            correlation_id=correlation_id,
        )
    except Exception:
        source.close()
        raise
    return GeneratedDocumentDownload(attempt=attempt, source=source)
