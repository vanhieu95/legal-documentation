from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from apps.documents.limits import MAX_TEMPLATE_BYTES
from apps.documents.package_validation import validate_docx_package
from apps.documents.registry import OutputStructureContract

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{_WORD_NAMESPACE}}}"
_TOKEN = re.compile(r"{{.*?}}|{%.*?%}|{#.*?#}", re.DOTALL)
_DELIMITER = re.compile(r"{{|}}|{%|%}|{#|#}")


class InvalidRenderedDocument(ValueError):
    """The rendered bytes are not a safe, structurally valid DOCX result."""


@dataclass(frozen=True, slots=True)
class DocumentStructure:
    parts: tuple[str, ...]
    text_parts: tuple[str, ...]
    paragraph_count: int
    table_count: int
    header_count: int
    footer_count: int
    section_count: int
    page_break_count: int
    has_styles: bool


def _is_word_xml(name: str) -> bool:
    return name.startswith("word/") and PurePosixPath(name).suffix.casefold() == ".xml"


def _is_text_part(name: str) -> bool:
    return (
        name == "word/document.xml"
        or name in {"word/footnotes.xml", "word/endnotes.xml"}
        or (name.startswith("word/header") and name.endswith(".xml"))
        or (name.startswith("word/footer") and name.endswith(".xml"))
    )


def _visible_text(root: ET.Element) -> str:
    return "".join(element.text or "" for element in root.iter(f"{_W}t"))


def _token_counts(root: ET.Element) -> Counter[str]:
    serialized = ET.tostring(root, encoding="unicode")
    visible = _visible_text(root)
    serialized_counts = _suspicious_counts(serialized)
    visible_counts = _suspicious_counts(visible)
    return serialized_counts | visible_counts


def _suspicious_counts(value: str) -> Counter[str]:
    tokens = Counter(_TOKEN.findall(value))
    tokens.update(_DELIMITER.findall(_TOKEN.sub("", value)))
    return tokens


def _page_break_count(root: ET.Element) -> int:
    return (
        sum(1 for element in root.iter(f"{_W}br") if element.get(f"{_W}type") == "page")
        + sum(1 for _ in root.iter(f"{_W}lastRenderedPageBreak"))
        + sum(1 for _ in root.iter(f"{_W}pageBreakBefore"))
    )


def inspect_rendered_docx(
    rendered_bytes: bytes,
    *,
    template_bytes: bytes,
    structure_contract: OutputStructureContract | None = None,
    literal_tokens_by_part: Mapping[str, Mapping[str, int]] | None = None,
) -> DocumentStructure:
    """Validate output package integrity and inventory contract-significant Word structure."""
    if not rendered_bytes or len(rendered_bytes) > MAX_TEMPLATE_BYTES:
        raise InvalidRenderedDocument("The rendered document size is invalid.")
    package_result = validate_docx_package(rendered_bytes)
    if not package_result.is_valid:
        raise InvalidRenderedDocument("The rendered document package is invalid.")

    try:
        with ZipFile(io.BytesIO(template_bytes)) as template_archive:
            template_parts = set(template_archive.namelist())
        with ZipFile(io.BytesIO(rendered_bytes)) as archive:
            parts = set(archive.namelist())
            protected_parts = {
                name
                for name in template_parts
                if name.startswith("word/")
                and PurePosixPath(name).suffix.casefold() in {".xml", ".rels"}
            }
            if not protected_parts.issubset(parts):
                raise InvalidRenderedDocument("The rendered document lost a protected Word part.")

            text_parts: list[str] = []
            paragraph_count = 0
            table_count = 0
            section_count = 0
            page_break_count = 0
            allowed_tokens = literal_tokens_by_part or {}
            for name in sorted(parts):
                if not _is_word_xml(name):
                    continue
                content = archive.read(name)
                root = ET.fromstring(content)
                tokens = _token_counts(root)
                part_allowance = allowed_tokens.get(name, {})
                if any(count > part_allowance.get(token, 0) for token, count in tokens.items()):
                    raise InvalidRenderedDocument(
                        "The rendered document contains an unresolved template token."
                    )
                if not _is_text_part(name):
                    continue
                text_parts.append(name)
                paragraph_count += sum(1 for _ in root.iter(f"{_W}p"))
                table_count += sum(1 for _ in root.iter(f"{_W}tbl"))
                section_count += sum(1 for _ in root.iter(f"{_W}sectPr"))
                page_break_count += _page_break_count(root)
    except InvalidRenderedDocument:
        raise
    except (BadZipFile, KeyError, OSError, ET.ParseError, ValueError) as error:
        raise InvalidRenderedDocument("The rendered document structure is invalid.") from error

    contract = structure_contract or OutputStructureContract()
    if (
        paragraph_count < contract.minimum_paragraphs
        or table_count < contract.minimum_tables
        or sum(name.startswith("word/header") for name in text_parts) < contract.minimum_headers
        or sum(name.startswith("word/footer") for name in text_parts) < contract.minimum_footers
        or section_count < contract.minimum_sections
        or page_break_count < contract.minimum_page_breaks
        or not contract.required_parts.issubset(parts)
    ):
        raise InvalidRenderedDocument("The rendered document lacks required Word structure.")
    return DocumentStructure(
        parts=tuple(sorted(parts)),
        text_parts=tuple(text_parts),
        paragraph_count=paragraph_count,
        table_count=table_count,
        header_count=sum(name.startswith("word/header") for name in text_parts),
        footer_count=sum(name.startswith("word/footer") for name in text_parts),
        section_count=section_count,
        page_break_count=page_break_count,
        has_styles="word/styles.xml" in parts,
    )
