from __future__ import annotations

import hashlib
import io
import re
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, cast
from zipfile import ZipFile

from apps.documents.models import GeneratedDocument
from apps.documents.output_validation import (
    DocumentStructure,
    InvalidRenderedDocument,
    inspect_rendered_docx,
)
from apps.documents.registry import (
    DocumentRegistration,
    InvalidDocumentRegistration,
    UnknownDocumentTypeKey,
    document_registry,
    matches_placeholder_value_kind,
)
from apps.documents.template_validation import create_restricted_environment, validate_template

_TOKEN = re.compile(r"{{.*?}}|{%.*?%}|{#.*?#}", re.DOTALL)
_TOKEN_OR_DELIMITER = re.compile(r"{{.*?}}|{%.*?%}|{#.*?#}|{{|}}|{%|%}|{#|#}", re.DOTALL)
_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_WORD_TEXT = f"{{{_WORD_NAMESPACE}}}t"


class _DocxTemplate(Protocol):
    def __init__(self, template_file: str) -> None: ...

    def render(self, context: Mapping[str, object], *, jinja_env: object) -> None: ...

    def save(self, target: str) -> None: ...


DocxTemplate = cast(type[_DocxTemplate], import_module("docxtpl").DocxTemplate)


class GenerationRenderCategory(StrEnum):
    TEMPLATE_INVALID = "template_invalid"
    CONTEXT_MISSING = "context_missing"
    RENDER_ERROR = "render_error"
    INTEGRITY_ERROR = "integrity_error"


class GenerationRenderError(ValueError):
    """A bounded generation-stage failure safe for lifecycle categorization."""

    def __init__(self, category: GenerationRenderCategory) -> None:
        super().__init__("The document could not be rendered safely.")
        self.category = category


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    content: bytes
    checksum_sha256: str
    byte_size: int
    structure: DocumentStructure


def generation_snapshot_values(attempt: GeneratedDocument) -> Mapping[str, object]:
    """Rebuild mapper input with immutable shared facts overridden by reviewed draft facts."""
    resolved = attempt.resolved_values_snapshot.get("values")
    inputs = attempt.input_snapshot.get("values")
    if not isinstance(resolved, dict) or not isinstance(inputs, dict):
        raise GenerationRenderError(GenerationRenderCategory.CONTEXT_MISSING)
    return MappingProxyType({**resolved, **inputs})


def _validated_context(
    registration: DocumentRegistration,
    values: Mapping[str, object],
) -> Mapping[str, Any]:
    try:
        context = registration.context_mapper(values)
    except Exception:
        raise GenerationRenderError(GenerationRenderCategory.CONTEXT_MISSING) from None
    contract = registration.placeholder_contract
    if (
        not isinstance(context, Mapping)
        or not contract.required_names.issubset(context)
        or not set(context).issubset(contract.expected_kinds)
        or any(
            not matches_placeholder_value_kind(value, contract.expected_kinds[name])
            for name, value in context.items()
        )
    ):
        raise GenerationRenderError(GenerationRenderCategory.CONTEXT_MISSING)
    return MappingProxyType(dict(context))


def _nested_context(flat_context: Mapping[str, Any]) -> dict[str, object]:
    nested: dict[str, object] = {}
    for dotted_name, value in flat_context.items():
        current = nested
        for part in dotted_name.split(".")[:-1]:
            child = current.setdefault(part, {})
            if not isinstance(child, dict):
                raise GenerationRenderError(GenerationRenderCategory.CONTEXT_MISSING)
            current = child
        current[dotted_name.rsplit(".", 1)[-1]] = value
    return nested


def _shadow_literal_tokens(value: object) -> object:
    if isinstance(value, str):
        return _TOKEN_OR_DELIMITER.sub(lambda match: "0" * len(match.group(0)), value)
    if isinstance(value, Mapping):
        return {key: _shadow_literal_tokens(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_shadow_literal_tokens(nested) for nested in value]
    if isinstance(value, tuple):
        return tuple(_shadow_literal_tokens(nested) for nested in value)
    return value


def _token_counts_by_part(package: bytes) -> dict[str, Counter[str]]:
    counts_by_part: dict[str, Counter[str]] = {}
    with ZipFile(io.BytesIO(package)) as archive:
        for name in archive.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            root = ET.fromstring(archive.read(name))
            serialized = ET.tostring(root, encoding="unicode")
            visible = "".join(element.text or "" for element in root.iter(_WORD_TEXT))
            tokens = _suspicious_counts(serialized) | _suspicious_counts(visible)
            if tokens:
                counts_by_part[name] = tokens
    return counts_by_part


def _suspicious_counts(value: str) -> Counter[str]:
    tokens = Counter(_TOKEN.findall(value))
    tokens.update(_TOKEN_OR_DELIMITER.findall(_TOKEN.sub("", value)))
    return tokens


def _literal_token_allowance(
    actual_package: bytes,
    shadow_package: bytes,
) -> dict[str, Counter[str]]:
    actual_counts = _token_counts_by_part(actual_package)
    shadow_counts = _token_counts_by_part(shadow_package)
    return {
        name: counts - shadow_counts.get(name, Counter())
        for name, counts in actual_counts.items()
        if counts - shadow_counts.get(name, Counter())
    }


def _registration_for(attempt: GeneratedDocument) -> DocumentRegistration:
    try:
        registration = document_registry.get(attempt.type_key)
    except (UnknownDocumentTypeKey, InvalidDocumentRegistration):
        raise GenerationRenderError(GenerationRenderCategory.TEMPLATE_INVALID) from None
    if not registration.enabled or registration.schema_version != attempt.schema_version:
        raise GenerationRenderError(GenerationRenderCategory.TEMPLATE_INVALID)
    return registration


def _verify_template_identity(attempt: GeneratedDocument, template_bytes: bytes) -> None:
    identity = attempt.template_snapshot.get("identity")
    checksum = hashlib.sha256(template_bytes).hexdigest()
    expected = {
        "id": str(attempt.template_version_id),
        "type_key": attempt.template_version.type_key,
        "version": attempt.template_version.version,
        "checksum_sha256": attempt.template_version.checksum_sha256,
    }
    if (
        attempt.status != GeneratedDocument.Status.GENERATING
        or identity != expected
        or attempt.type_key != attempt.template_version.type_key
        or checksum != attempt.template_version.checksum_sha256
        or len(template_bytes) != attempt.template_version.byte_size
    ):
        raise GenerationRenderError(GenerationRenderCategory.INTEGRITY_ERROR)


def render_reserved_generation(
    *,
    attempt: GeneratedDocument,
    template_bytes: bytes,
) -> RenderedDocument:
    """Render and inspect one reserved attempt without database or durable storage writes."""
    _verify_template_identity(attempt, template_bytes)
    registration = _registration_for(attempt)
    validation = validate_template(template_bytes, registration)
    if not validation.is_valid:
        raise GenerationRenderError(GenerationRenderCategory.TEMPLATE_INVALID)
    values = generation_snapshot_values(attempt)
    context = _validated_context(registration, values)
    shadow_context = _shadow_literal_tokens(context)
    if not isinstance(shadow_context, Mapping):
        raise GenerationRenderError(GenerationRenderCategory.CONTEXT_MISSING)

    with tempfile.TemporaryDirectory(prefix="vds-generation-render-") as temporary_name:
        source_path = Path(temporary_name) / "template.docx"
        output_path = Path(temporary_name) / "rendered.docx"
        shadow_path = Path(temporary_name) / "shadow.docx"
        try:
            source_path.write_bytes(template_bytes)
            document = DocxTemplate(str(source_path))
            document.render(
                _nested_context(context),
                jinja_env=create_restricted_environment(registration.placeholder_contract),
            )
            document.save(str(output_path))
            shadow_document = DocxTemplate(str(source_path))
            shadow_document.render(
                _nested_context(shadow_context),
                jinja_env=create_restricted_environment(registration.placeholder_contract),
            )
            shadow_document.save(str(shadow_path))
            rendered_bytes = output_path.read_bytes()
            shadow_bytes = shadow_path.read_bytes()
            try:
                inspect_rendered_docx(
                    shadow_bytes,
                    template_bytes=template_bytes,
                    structure_contract=registration.output_structure_contract,
                )
                literal_provenance = _literal_token_allowance(rendered_bytes, shadow_bytes)
                inspect_rendered_docx(
                    rendered_bytes,
                    template_bytes=template_bytes,
                    structure_contract=registration.output_structure_contract,
                    literal_tokens_by_part=literal_provenance,
                )
            except (InvalidRenderedDocument, ET.ParseError, OSError, ValueError):
                raise GenerationRenderError(GenerationRenderCategory.INTEGRITY_ERROR) from None
            if registration.post_processor_name is not None:
                processor = document_registry.get_post_processor(registration.post_processor_name)
                processor(str(output_path))
            rendered_bytes = output_path.read_bytes()
        except GenerationRenderError:
            raise
        except Exception:
            raise GenerationRenderError(GenerationRenderCategory.RENDER_ERROR) from None

        try:
            structure = inspect_rendered_docx(
                rendered_bytes,
                template_bytes=template_bytes,
                structure_contract=registration.output_structure_contract,
                literal_tokens_by_part=literal_provenance,
            )
        except InvalidRenderedDocument:
            raise GenerationRenderError(GenerationRenderCategory.INTEGRITY_ERROR) from None

    return RenderedDocument(
        content=rendered_bytes,
        checksum_sha256=hashlib.sha256(rendered_bytes).hexdigest(),
        byte_size=len(rendered_bytes),
        structure=structure,
    )
