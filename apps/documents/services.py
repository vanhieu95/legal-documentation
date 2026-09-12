from __future__ import annotations

import hashlib
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO
from zipfile import BadZipFile, ZipFile

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.storage import Storage, storages
from django.db import IntegrityError, transaction
from docxtpl import DocxTemplate  # type: ignore[import-untyped]

from apps.accounts.policies import ApplicationPermission, service_permission_required
from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.recorder import AuditTarget, record_audit_event
from apps.documents.limits import MAX_TEMPLATE_BYTES
from apps.documents.models import TemplateVersion
from apps.documents.package_validation import PackageFinding, validate_docx_package
from apps.documents.registry import (
    DocumentRegistration,
    UnknownDocumentTypeKey,
    document_registry,
)
from apps.documents.storage_keys import (
    build_template_storage_key,
    sanitize_template_display_filename,
)
from apps.documents.template_validation import (
    TemplateFinding,
    create_restricted_environment,
    validate_template,
)

_READ_CHUNK_SIZE = 64 * 1024
_UNRESOLVED_TOKENS = (b"{{", b"}}", b"{%", b"%}", b"{#", b"#}")
_RELEVANT_WORD_PARTS = (
    "word/document.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
)


class TemplateUploadError(ValueError):
    """Base class for safe template-upload failures."""


class UnknownOrDisabledDocumentType(TemplateUploadError):
    """Raised when a request key is not an enabled deployed registration."""


class DuplicateTemplateVersion(TemplateUploadError):
    """Raised when a type/version identity already exists."""


class InvalidTemplateUpload(TemplateUploadError):
    """Raised when upload metadata or the bounded input stream is invalid."""


class TemplateStorageError(TemplateUploadError):
    """Raised when immutable private placement cannot be completed."""


def _registration(type_key: str) -> DocumentRegistration:
    try:
        registration = document_registry.get(type_key)
    except UnknownDocumentTypeKey as error:
        raise UnknownOrDisabledDocumentType("Document type is unavailable.") from error
    if not registration.enabled:
        raise UnknownOrDisabledDocumentType("Document type is unavailable.")
    return registration


def _safe_upload_metadata(version: str, approval_reference: str, filename: str) -> tuple[str, str]:
    if not approval_reference.strip():
        raise InvalidTemplateUpload("An approval reference is required.")
    display_filename = sanitize_template_display_filename(filename)
    if not display_filename.casefold().endswith(".docx"):
        raise InvalidTemplateUpload("A DOCX upload is required.")
    if not version or len(version) > 64:
        raise InvalidTemplateUpload("A valid template version is required.")
    return approval_reference.strip(), display_filename


def _copy_bounded_upload(source: BinaryIO, destination: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_size = 0
    try:
        with destination.open("xb") as output:
            while byte_size <= MAX_TEMPLATE_BYTES:
                requested = min(_READ_CHUNK_SIZE, MAX_TEMPLATE_BYTES + 1 - byte_size)
                chunk = source.read(requested)
                if not chunk:
                    break
                if not isinstance(chunk, bytes) or len(chunk) > requested:
                    raise InvalidTemplateUpload("The upload stream is invalid.")
                output.write(chunk)
                digest.update(chunk)
                byte_size += len(chunk)
    except InvalidTemplateUpload:
        raise
    except Exception as error:
        raise InvalidTemplateUpload("The upload could not be read.") from error
    if byte_size == 0:
        raise InvalidTemplateUpload("The upload is empty.")
    if byte_size > MAX_TEMPLATE_BYTES:
        raise InvalidTemplateUpload("The upload exceeds the allowed size.")
    return digest.hexdigest(), byte_size


def _audit(
    *,
    action: AuditAction,
    outcome: AuditOutcome,
    actor: User,
    correlation_id: str,
    template: TemplateVersion | None,
    type_key: str,
    version: str,
    reason_code: str | None = None,
) -> None:
    metadata: dict[str, object] = {"type_key": type_key, "version": version}
    if reason_code is not None:
        metadata["reason_code"] = reason_code
    record_audit_event(
        action=action,
        outcome=outcome,
        actor=actor,
        target=AuditTarget(
            type=AuditTargetType.TEMPLATE_VERSION,
            id=str(template.pk) if template is not None else "",
        ),
        correlation_id=correlation_id,
        metadata=metadata,
    )


def _report(result: str, categories: list[str], *, render_count: int = 0) -> dict[str, object]:
    bounded_categories = sorted(set(categories))[:50]
    counts = Counter(categories)
    if render_count:
        counts["synthetic_renders"] = render_count
    return {
        "schema_version": 1,
        "result": result,
        "categories": bounded_categories,
        "counts": dict(sorted(counts.items())),
    }


def _finding_categories(findings: tuple[PackageFinding | TemplateFinding, ...]) -> list[str]:
    return [str(finding.category) for finding in findings]


def _nested_context(flat_context: Mapping[str, Any]) -> dict[str, object]:
    nested: dict[str, object] = {}
    for dotted_name, value in flat_context.items():
        parts = dotted_name.split(".")
        current = nested
        for part in parts[:-1]:
            existing = current.setdefault(part, {})
            if not isinstance(existing, dict):
                raise ValueError("Synthetic context has conflicting placeholder paths.")
            current = existing
        current[parts[-1]] = value
    return nested


def _supported_word_parts(archive: ZipFile) -> tuple[str, ...]:
    names = set(archive.namelist())
    parts = [name for name in _RELEVANT_WORD_PARTS if name in names]
    parts.extend(
        sorted(name for name in names if name.startswith("word/header") and name.endswith(".xml"))
    )
    parts.extend(
        sorted(name for name in names if name.startswith("word/footer") and name.endswith(".xml"))
    )
    return tuple(parts)


def _inspect_rendered_output(
    output_path: Path,
    *,
    expected_parts: tuple[str, ...],
    expected_unicode: tuple[str, ...],
) -> tuple[str, ...]:
    if output_path.stat().st_size > MAX_TEMPLATE_BYTES:
        return ("rendered_size_limit",)
    output = output_path.read_bytes()
    package_result = validate_docx_package(output)
    if not package_result.is_valid:
        return tuple(sorted(set(_finding_categories(package_result.findings))))
    try:
        with ZipFile(output_path) as archive:
            names = set(archive.namelist())
            if any(part not in names for part in expected_parts):
                return ("rendered_part_missing",)
            text = b"\n".join(archive.read(part) for part in expected_parts)
    except (BadZipFile, KeyError, OSError):
        return ("rendered_package_invalid",)
    if any(token in text for token in _UNRESOLVED_TOKENS):
        return ("unresolved_token",)
    decoded = text.decode("utf-8", errors="replace")
    if expected_unicode and not all(value in decoded for value in expected_unicode):
        return ("unicode_missing",)
    return ()


def _render_and_inspect(
    source_path: Path,
    output_path: Path,
    registration: DocumentRegistration,
    fixture_values: Mapping[str, Any],
    expected_parts: tuple[str, ...],
) -> tuple[str, ...]:
    flat_context = registration.context_mapper(fixture_values)
    environment = create_restricted_environment(registration.placeholder_contract)
    document = DocxTemplate(str(source_path))
    document.render(_nested_context(flat_context), jinja_env=environment)
    document.save(str(output_path))
    expected_unicode = tuple(
        value
        for value in flat_context.values()
        if isinstance(value, str) and any(ord(character) > 127 for character in value)
    )
    return _inspect_rendered_output(
        output_path,
        expected_parts=expected_parts,
        expected_unicode=expected_unicode,
    )


def _validate_and_render(
    package: bytes,
    source_path: Path,
    work_directory: Path,
    registration: DocumentRegistration,
) -> tuple[dict[str, object], TemplateVersion.Status]:
    package_result = validate_docx_package(package)
    if not package_result.is_valid:
        categories = _finding_categories(package_result.findings)
        return _report("invalid", categories), TemplateVersion.Status.INVALID

    template_result = validate_template(package, registration)
    if not template_result.is_valid:
        categories = _finding_categories(template_result.findings)
        return _report("invalid", categories), TemplateVersion.Status.INVALID

    with ZipFile(source_path) as archive:
        expected_parts = _supported_word_parts(archive)
    render_categories: list[str] = []
    for index, fixture in enumerate(
        (registration.minimal_fixture(), registration.representative_fixture()), start=1
    ):
        output_path = work_directory / f"synthetic-output-{index}.docx"
        render_categories.extend(
            _render_and_inspect(source_path, output_path, registration, fixture, expected_parts)
        )
    if render_categories:
        return _report("invalid", render_categories), TemplateVersion.Status.INVALID
    return _report("valid", [], render_count=2), TemplateVersion.Status.VALID


@service_permission_required(ApplicationPermission.UPLOAD_TEMPLATES)
@service_permission_required(ApplicationPermission.VALIDATE_TEMPLATES)
def upload_and_validate_template(
    *,
    actor: User,
    type_key: str,
    version: str,
    approval_reference: str,
    uploaded_file: BinaryIO,
    original_filename: str,
    correlation_id: str,
    storage: Storage | None = None,
) -> TemplateVersion:
    """Store and validate one immutable proposed version without activating it."""
    registration = _registration(type_key)
    approval_reference, display_filename = _safe_upload_metadata(
        version, approval_reference, original_filename
    )
    if TemplateVersion.objects.filter(type_key=type_key, version=version).exists():
        raise DuplicateTemplateVersion("The template version already exists.")

    private_storage = storage or storages["private"]
    storage_key = build_template_storage_key(type_key, version)
    saved_key: str | None = None
    template: TemplateVersion | None = None
    with tempfile.TemporaryDirectory(prefix="vds-template-validation-") as temporary_name:
        work_directory = Path(temporary_name)
        source_path = work_directory / "proposed.docx"
        try:
            checksum, byte_size = _copy_bounded_upload(uploaded_file, source_path)
        except InvalidTemplateUpload:
            _audit(
                action=AuditAction.TEMPLATE_UPLOADED,
                outcome=AuditOutcome.FAILURE,
                actor=actor,
                correlation_id=correlation_id,
                template=None,
                type_key=type_key,
                version=version,
                reason_code="read_error",
            )
            raise

        try:
            with source_path.open("rb") as source:
                saved_key = private_storage.save(storage_key, File(source))
            if saved_key != storage_key:
                raise OSError("Private storage changed the immutable key.")
            with transaction.atomic():
                template = TemplateVersion.objects.create(
                    type_key=type_key,
                    version=version,
                    storage_key=storage_key,
                    original_filename=display_filename,
                    checksum_sha256=checksum,
                    byte_size=byte_size,
                    uploader=actor,
                    approval_reference=approval_reference,
                )
                _audit(
                    action=AuditAction.TEMPLATE_UPLOADED,
                    outcome=AuditOutcome.SUCCESS,
                    actor=actor,
                    correlation_id=correlation_id,
                    template=template,
                    type_key=type_key,
                    version=version,
                )
        except (OSError, ValidationError, IntegrityError) as error:
            cleanup_keys = {storage_key}
            if saved_key is not None:
                cleanup_keys.add(saved_key)
            for cleanup_key in cleanup_keys:
                if private_storage.exists(cleanup_key):
                    private_storage.delete(cleanup_key)
            _audit(
                action=AuditAction.TEMPLATE_UPLOADED,
                outcome=AuditOutcome.FAILURE,
                actor=actor,
                correlation_id=correlation_id,
                template=None,
                type_key=type_key,
                version=version,
                reason_code="storage_error",
            )
            if isinstance(error, IntegrityError):
                raise DuplicateTemplateVersion("The template version already exists.") from error
            raise TemplateStorageError("The template could not be stored.") from error

        assert template is not None
        package = source_path.read_bytes()
        try:
            report, status = _validate_and_render(
                package, source_path, work_directory, registration
            )
        except Exception:
            report = _report("invalid", ["render_error"])
            status = TemplateVersion.Status.INVALID

        with transaction.atomic():
            template.validation_report = report
            template.save(update_fields=("validation_report",))
            template.transition_to(status)
            _audit(
                action=AuditAction.TEMPLATE_VALIDATED,
                outcome=(
                    AuditOutcome.SUCCESS
                    if status == TemplateVersion.Status.VALID
                    else AuditOutcome.FAILURE
                ),
                actor=actor,
                correlation_id=correlation_id,
                template=template,
                type_key=type_key,
                version=version,
                reason_code=(
                    None if status == TemplateVersion.Status.VALID else "validation_failed"
                ),
            )
    return template
