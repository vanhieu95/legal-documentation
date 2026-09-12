from __future__ import annotations

import io
import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import BinaryIO, NoReturn
from urllib.parse import unquote, urlsplit
from xml.parsers import expat
from zipfile import BadZipFile, LargeZipFile, ZipFile, ZipInfo

from apps.documents.limits import (
    DEFAULT_PACKAGE_LIMITS,
    MAX_PACKAGE_FINDINGS,
    PackageValidationLimits,
)

_CONTENT_TYPES = "[Content_Types].xml"
_ROOT_RELATIONSHIPS = "_rels/.rels"
_MAIN_DOCUMENT = "word/document.xml"
_REQUIRED_PARTS = frozenset({_CONTENT_TYPES, _ROOT_RELATIONSHIPS, _MAIN_DOCUMENT})
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_UNSAFE_PATH_CHARACTERS = re.compile(r"[\x00-\x1f\x7f<>:\"|?*]")
_EXECUTABLE_SUFFIXES = frozenset(
    {".bat", ".cmd", ".com", ".dll", ".exe", ".js", ".msi", ".ps1", ".scr", ".vbs"}
)
_CONTENT_TYPE_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"
_RELATIONSHIP_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
_WORDPROCESSING_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_WORD_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
_OFFICE_DOCUMENT_RELATIONSHIP = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)
_XML_MARKUP_PATTERN = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_RELATIONSHIP_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_SAFE_OFFICE_RELATIONSHIP_KINDS = frozenset(
    {
        "comments",
        "commentsExtended",
        "customXml",
        "endnotes",
        "extended-properties",
        "custom-properties",
        "fontTable",
        "footer",
        "footnotes",
        "glossaryDocument",
        "header",
        "image",
        "numbering",
        "officeDocument",
        "people",
        "settings",
        "styles",
        "theme",
        "webSettings",
    }
)
_SAFE_PACKAGE_RELATIONSHIPS = frozenset(
    {
        "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
    }
)


class PackageErrorCategory(StrEnum):
    NOT_ZIP = "not_zip"
    CORRUPT_ZIP = "corrupt_zip"
    INTERRUPTED_READ = "interrupted_read"
    COMPRESSED_SIZE_LIMIT = "compressed_size_limit"
    ENTRY_COUNT_LIMIT = "entry_count_limit"
    TOTAL_SIZE_LIMIT = "total_size_limit"
    ENTRY_SIZE_LIMIT = "entry_size_limit"
    COMPRESSION_RATIO_LIMIT = "compression_ratio_limit"
    UNSAFE_ENTRY_NAME = "unsafe_entry_name"
    DUPLICATE_ENTRY = "duplicate_entry"
    CASE_COLLISION = "case_collision"
    UNSUPPORTED_STRUCTURE = "unsupported_structure"
    MISSING_REQUIRED_PART = "missing_required_part"
    ENCRYPTED_ENTRY = "encrypted_entry"
    MACRO_CONTENT = "macro_content"
    ACTIVEX_CONTENT = "activex_content"
    OLE_CONTENT = "ole_content"
    EMBEDDED_CONTENT = "embedded_content"
    EXECUTABLE_CONTENT = "executable_content"
    PROHIBITED_BINARY = "prohibited_binary"
    XML_SIZE_LIMIT = "xml_size_limit"
    XML_DTD_PROHIBITED = "xml_dtd_prohibited"
    XML_DEPTH_LIMIT = "xml_depth_limit"
    MALFORMED_XML = "malformed_xml"
    INVALID_CONTENT_TYPES = "invalid_content_types"
    INVALID_WORD_DOCUMENT = "invalid_word_document"
    MALFORMED_RELATIONSHIPS = "malformed_relationships"
    EXTERNAL_RELATIONSHIP = "external_relationship"
    UNSAFE_RELATIONSHIP_TARGET = "unsafe_relationship_target"
    MISSING_RELATIONSHIP_TARGET = "missing_relationship_target"


@dataclass(frozen=True, slots=True, order=True)
class PackageFinding:
    category: PackageErrorCategory
    location: str


@dataclass(frozen=True, slots=True)
class PackageValidationResult:
    findings: tuple[PackageFinding, ...]

    @property
    def is_valid(self) -> bool:
        return not self.findings


def _finding(category: PackageErrorCategory, location: str = "package") -> PackageFinding:
    return PackageFinding(category=category, location=location[:160])


def _result(findings: list[PackageFinding] | tuple[PackageFinding, ...]) -> PackageValidationResult:
    return PackageValidationResult(tuple(sorted(set(findings)))[:MAX_PACKAGE_FINDINGS])


def _read_package(
    source: bytes | bytearray | memoryview | BinaryIO, limits: PackageValidationLimits
) -> tuple[bytes | None, PackageFinding | None]:
    if isinstance(source, (bytes, bytearray, memoryview)):
        package = bytes(source)
        if len(package) > limits.max_compressed_bytes:
            return None, _finding(PackageErrorCategory.COMPRESSED_SIZE_LIMIT)
        return package, None
    try:
        chunks: list[bytes] = []
        bytes_read = 0
        while bytes_read <= limits.max_compressed_bytes:
            requested = min(64 * 1024, limits.max_compressed_bytes + 1 - bytes_read)
            chunk = source.read(requested)
            if not chunk:
                return b"".join(chunks), None
            if not isinstance(chunk, bytes):
                return None, _finding(PackageErrorCategory.INTERRUPTED_READ)
            if len(chunk) > requested:
                return None, _finding(PackageErrorCategory.COMPRESSED_SIZE_LIMIT)
            chunks.append(chunk)
            bytes_read += len(chunk)
        return None, _finding(PackageErrorCategory.COMPRESSED_SIZE_LIMIT)
    except Exception:
        return None, _finding(PackageErrorCategory.INTERRUPTED_READ)


def _decoded_name(name: str) -> str:
    decoded = unicodedata.normalize("NFKC", name)
    while True:
        expanded = unquote(decoded)
        if expanded == decoded:
            return unicodedata.normalize("NFKC", decoded)
        decoded = expanded


def _normalized_entry_name(name: str) -> str | None:
    decoded = _decoded_name(name)
    if (
        not decoded
        or decoded.startswith(("/", "\\"))
        or "\\" in decoded
        or _UNSAFE_PATH_CHARACTERS.search(decoded)
    ):
        return None
    parts = decoded.rstrip("/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return posixpath.normpath(decoded.rstrip("/"))


def _structure_is_allowed(name: str) -> bool:
    if name in {_CONTENT_TYPES, _ROOT_RELATIONSHIPS}:
        return True
    if name.startswith("docProps/"):
        return name.endswith(".xml")
    if not name.startswith("word/"):
        return False
    return PurePosixPath(name).suffix.casefold() in {
        ".xml",
        ".rels",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
        ".emf",
        ".wmf",
        ".odttf",
    }


def _prohibited_name_category(name: str) -> PackageErrorCategory | None:
    folded = name.casefold()
    suffix = PurePosixPath(folded).suffix
    if "vbaproject" in folded or "macros/" in folded:
        return PackageErrorCategory.MACRO_CONTENT
    if folded.startswith("word/activex/"):
        return PackageErrorCategory.ACTIVEX_CONTENT
    if "oleobject" in folded:
        return PackageErrorCategory.OLE_CONTENT
    if folded.startswith("word/embeddings/") or "/embeddings/" in folded:
        return PackageErrorCategory.EMBEDDED_CONTENT
    if suffix in _EXECUTABLE_SUFFIXES:
        return PackageErrorCategory.EXECUTABLE_CONTENT
    if suffix == ".bin":
        return PackageErrorCategory.PROHIBITED_BINARY
    return None


class _XmlDtdProhibited(Exception):
    pass


class _XmlDepthExceeded(Exception):
    pass


def _decode_xml_for_scan(content: bytes) -> str:
    if content.startswith((b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")):
        return content.decode("utf-32")
    if content.startswith((b"\xfe\xff", b"\xff\xfe")):
        return content.decode("utf-16")
    if content.startswith(b"\x00<"):
        return content.decode("utf-16-be")
    if content.startswith(b"<\x00"):
        return content.decode("utf-16-le")
    return content.decode("utf-8-sig")


def _preflight_xml(content: bytes, max_depth: int) -> PackageErrorCategory | None:
    try:
        text = _decode_xml_for_scan(content)
    except UnicodeDecodeError:
        return PackageErrorCategory.MALFORMED_XML
    if _XML_MARKUP_PATTERN.search(text):
        return PackageErrorCategory.XML_DTD_PROHIBITED

    depth = -1

    def start_element(_name: str, _attributes: dict[str, str]) -> None:
        nonlocal depth
        depth += 1
        if depth > max_depth:
            raise _XmlDepthExceeded

    def end_element(_name: str) -> None:
        nonlocal depth
        depth -= 1

    def reject_dtd(*_args: object) -> NoReturn:
        raise _XmlDtdProhibited

    parser = expat.ParserCreate()
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    parser.StartDoctypeDeclHandler = reject_dtd
    parser.EntityDeclHandler = reject_dtd
    parser.ExternalEntityRefHandler = reject_dtd
    try:
        parser.Parse(content, True)
    except _XmlDtdProhibited:
        return PackageErrorCategory.XML_DTD_PROHIBITED
    except _XmlDepthExceeded:
        return PackageErrorCategory.XML_DEPTH_LIMIT
    except expat.ExpatError:
        return PackageErrorCategory.MALFORMED_XML
    return None


def _safe_xml(
    content: bytes,
    *,
    location: str,
    limits: PackageValidationLimits,
) -> tuple[ET.Element | None, PackageFinding | None]:
    if len(content) > limits.max_xml_bytes:
        return None, _finding(PackageErrorCategory.XML_SIZE_LIMIT, location)
    if category := _preflight_xml(content, limits.max_xml_depth):
        return None, _finding(category, location)
    try:
        return ET.fromstring(content), None
    except (ET.ParseError, ValueError):
        return None, _finding(PackageErrorCategory.MALFORMED_XML, location)


def _inspect_entry_metadata(
    entries: list[ZipInfo], limits: PackageValidationLimits
) -> tuple[list[PackageFinding], dict[str, ZipInfo]]:
    if len(entries) > limits.max_entries:
        return [_finding(PackageErrorCategory.ENTRY_COUNT_LIMIT)], {}
    findings: list[PackageFinding] = []
    normalized_entries: dict[str, ZipInfo] = {}
    casefolded_entries: dict[str, str] = {}
    total_size = 0
    for index, entry in enumerate(entries):
        location = f"entry:{index}"
        normalized = _normalized_entry_name(entry.filename)
        if normalized is None:
            findings.append(_finding(PackageErrorCategory.UNSAFE_ENTRY_NAME, location))
            continue
        if normalized in normalized_entries:
            findings.append(_finding(PackageErrorCategory.DUPLICATE_ENTRY, location))
            continue
        folded = normalized.casefold()
        if folded in casefolded_entries:
            findings.append(_finding(PackageErrorCategory.CASE_COLLISION, location))
            continue
        normalized_entries[normalized] = entry
        casefolded_entries[folded] = normalized
        total_size += entry.file_size
        if entry.flag_bits & 0x1:
            findings.append(_finding(PackageErrorCategory.ENCRYPTED_ENTRY, location))
        if entry.file_size > limits.max_entry_uncompressed_bytes:
            findings.append(_finding(PackageErrorCategory.ENTRY_SIZE_LIMIT, location))
        if total_size > limits.max_total_uncompressed_bytes:
            findings.append(_finding(PackageErrorCategory.TOTAL_SIZE_LIMIT))
        if (
            entry.file_size
            and entry.file_size / max(entry.compress_size, 1) > limits.max_compression_ratio
        ):
            findings.append(_finding(PackageErrorCategory.COMPRESSION_RATIO_LIMIT, location))
        if prohibited := _prohibited_name_category(normalized):
            findings.append(_finding(prohibited, location))
        elif not _structure_is_allowed(normalized):
            findings.append(_finding(PackageErrorCategory.UNSUPPORTED_STRUCTURE, location))
    return findings, normalized_entries


def _raw_central_directory(package: bytes) -> tuple[int, bool] | None:
    end_record = package.rfind(b"PK\x05\x06")
    if end_record < 0 or end_record + 22 > len(package):
        return None
    expected_count = int.from_bytes(package[end_record + 10 : end_record + 12], "little")
    central_size = int.from_bytes(package[end_record + 12 : end_record + 16], "little")
    offset = int.from_bytes(package[end_record + 16 : end_record + 20], "little")
    central_end = offset + central_size
    count = 0
    has_nul = False
    while offset < central_end:
        if offset + 46 > len(package) or package[offset : offset + 4] != b"PK\x01\x02":
            return None
        name_length = int.from_bytes(package[offset + 28 : offset + 30], "little")
        extra_length = int.from_bytes(package[offset + 30 : offset + 32], "little")
        comment_length = int.from_bytes(package[offset + 32 : offset + 34], "little")
        name_start = offset + 46
        name_end = name_start + name_length
        if name_end > len(package):
            return None
        has_nul = has_nul or b"\x00" in package[name_start:name_end]
        count += 1
        offset = name_end + extra_length + comment_length
    if offset != central_end or count != expected_count:
        return None
    return count, has_nul


def _read_entries(
    archive: ZipFile,
    entries: dict[str, ZipInfo],
    limits: PackageValidationLimits,
) -> tuple[dict[str, bytes], list[PackageFinding]]:
    contents: dict[str, bytes] = {}
    findings: list[PackageFinding] = []
    for index, (name, entry) in enumerate(entries.items()):
        if entry.file_size > limits.max_entry_uncompressed_bytes:
            continue
        try:
            with archive.open(entry) as stream:
                content = stream.read(limits.max_entry_uncompressed_bytes + 1)
                if len(content) > limits.max_entry_uncompressed_bytes:
                    findings.append(
                        _finding(PackageErrorCategory.ENTRY_SIZE_LIMIT, f"entry:{index}")
                    )
                    continue
        except (BadZipFile, OSError, RuntimeError, ValueError):
            findings.append(_finding(PackageErrorCategory.CORRUPT_ZIP, f"entry:{index}"))
            continue
        contents[name] = content
    return contents, findings


def _prohibited_content_type(content_type: str) -> PackageErrorCategory | None:
    folded = content_type.casefold()
    if "macroenabled" in folded or "vba" in folded:
        return PackageErrorCategory.MACRO_CONTENT
    if "activex" in folded:
        return PackageErrorCategory.ACTIVEX_CONTENT
    if "oleobject" in folded:
        return PackageErrorCategory.OLE_CONTENT
    if "officedocument.package" in folded:
        return PackageErrorCategory.EMBEDDED_CONTENT
    if "executable" in folded or "x-msdownload" in folded:
        return PackageErrorCategory.EXECUTABLE_CONTENT
    return None


def _validate_content_types(root: ET.Element, entries: dict[str, ZipInfo]) -> list[PackageFinding]:
    if root.tag != f"{{{_CONTENT_TYPE_NAMESPACE}}}Types":
        return [_finding(PackageErrorCategory.INVALID_CONTENT_TYPES, "content_types")]
    findings: list[PackageFinding] = []
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    default_tag = f"{{{_CONTENT_TYPE_NAMESPACE}}}Default"
    override_tag = f"{{{_CONTENT_TYPE_NAMESPACE}}}Override"
    for child in root:
        if child.tag == default_tag:
            extension = child.get("Extension", "").casefold()
            content_type = child.get("ContentType", "")
            if (
                not extension
                or extension in defaults
                or set(child.attrib) != {"Extension", "ContentType"}
            ):
                findings.append(
                    _finding(PackageErrorCategory.INVALID_CONTENT_TYPES, "content_types")
                )
            defaults[extension] = content_type
        elif child.tag == override_tag:
            part_name = child.get("PartName", "")
            content_type = child.get("ContentType", "")
            if (
                not part_name.startswith("/")
                or part_name in overrides
                or set(child.attrib) != {"PartName", "ContentType"}
            ):
                findings.append(
                    _finding(PackageErrorCategory.INVALID_CONTENT_TYPES, "content_types")
                )
            overrides[part_name] = content_type
        else:
            findings.append(_finding(PackageErrorCategory.INVALID_CONTENT_TYPES, "content_types"))
    if defaults.get("rels") != "application/vnd.openxmlformats-package.relationships+xml":
        findings.append(_finding(PackageErrorCategory.INVALID_CONTENT_TYPES, "content_types"))
    if defaults.get("xml") != "application/xml":
        findings.append(_finding(PackageErrorCategory.INVALID_CONTENT_TYPES, "content_types"))
    for declaration, content_type in (*defaults.items(), *overrides.items()):
        if category := _prohibited_content_type(content_type):
            findings.append(_finding(category, "content_types"))
        if declaration.startswith("/") and declaration.lstrip("/") not in entries:
            findings.append(_finding(PackageErrorCategory.INVALID_CONTENT_TYPES, "content_types"))
    if overrides.get(f"/{_MAIN_DOCUMENT}") != _WORD_MAIN_CONTENT_TYPE:
        findings.append(_finding(PackageErrorCategory.INVALID_CONTENT_TYPES, "content_types"))
    for name in entries:
        if name == _CONTENT_TYPES:
            continue
        basename = PurePosixPath(name).name
        extension = basename.rsplit(".", 1)[-1].casefold() if "." in basename else ""
        if f"/{name}" not in overrides and extension not in defaults:
            findings.append(_finding(PackageErrorCategory.INVALID_CONTENT_TYPES, "content_types"))
    return findings


def _relationship_source(rels_name: str) -> str:
    if rels_name == _ROOT_RELATIONSHIPS:
        return ""
    parent = PurePosixPath(rels_name).parent.parent
    filename = PurePosixPath(rels_name).name.removesuffix(".rels")
    return posixpath.join(str(parent), filename)


def _relationship_type_is_safe(relationship_type: str) -> bool:
    if relationship_type in _SAFE_PACKAGE_RELATIONSHIPS:
        return True
    prefixes = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/",
        "http://purl.oclc.org/ooxml/officeDocument/relationships/",
    )
    return any(
        relationship_type == f"{prefix}{kind}"
        for prefix in prefixes
        for kind in _SAFE_OFFICE_RELATIONSHIP_KINDS
    )


def _validate_relationships(
    root: ET.Element,
    *,
    rels_name: str,
    entries: dict[str, ZipInfo],
) -> list[PackageFinding]:
    if root.tag != f"{{{_RELATIONSHIP_NAMESPACE}}}Relationships":
        return [_finding(PackageErrorCategory.MALFORMED_RELATIONSHIPS, "relationships")]
    findings: list[PackageFinding] = []
    source_directory = posixpath.dirname(_relationship_source(rels_name))
    office_document_count = 0
    relationship_ids: set[str] = set()
    for index, relationship in enumerate(root):
        location = f"relationship:{index}"
        if relationship.tag != f"{{{_RELATIONSHIP_NAMESPACE}}}Relationship":
            findings.append(_finding(PackageErrorCategory.MALFORMED_RELATIONSHIPS, location))
            continue
        target = relationship.get("Target", "")
        relationship_id = relationship.get("Id", "")
        relationship_type = relationship.get("Type", "")
        if (
            not target
            or not _RELATIONSHIP_ID.fullmatch(relationship_id)
            or relationship_id in relationship_ids
            or not _relationship_type_is_safe(relationship_type)
            or set(relationship.attrib).difference({"Id", "Type", "Target", "TargetMode"})
        ):
            findings.append(_finding(PackageErrorCategory.MALFORMED_RELATIONSHIPS, location))
            continue
        relationship_ids.add(relationship_id)
        target_mode = relationship.get("TargetMode")
        if target_mode == "External":
            findings.append(_finding(PackageErrorCategory.EXTERNAL_RELATIONSHIP, location))
            continue
        if target_mode not in {None, "Internal"}:
            findings.append(_finding(PackageErrorCategory.MALFORMED_RELATIONSHIPS, location))
            continue
        if (
            rels_name == _ROOT_RELATIONSHIPS
            and relationship_type == _OFFICE_DOCUMENT_RELATIONSHIP
            and target == _MAIN_DOCUMENT
        ):
            office_document_count += 1
        decoded = _decoded_name(target)
        parsed = urlsplit(decoded)
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or decoded.startswith(("/", "\\"))
            or "\\" in decoded
            or _UNSAFE_PATH_CHARACTERS.search(decoded)
            or any(part in {"", ".", ".."} for part in decoded.split("/"))
        ):
            findings.append(_finding(PackageErrorCategory.UNSAFE_RELATIONSHIP_TARGET, location))
            continue
        resolved = posixpath.normpath(posixpath.join(source_directory, decoded))
        if resolved not in entries:
            findings.append(_finding(PackageErrorCategory.MISSING_RELATIONSHIP_TARGET, location))
    if rels_name == _ROOT_RELATIONSHIPS and office_document_count != 1:
        findings.append(_finding(PackageErrorCategory.MALFORMED_RELATIONSHIPS, "relationships"))
    return findings


def _dangerous_magic(content: bytes) -> PackageErrorCategory | None:
    if content.startswith((b"MZ", b"\x7fELF")):
        return PackageErrorCategory.EXECUTABLE_CONTENT
    if content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return PackageErrorCategory.OLE_CONTENT
    if content.startswith(_ZIP_SIGNATURES):
        return PackageErrorCategory.EMBEDDED_CONTENT
    return None


def _validate_word_document(root: ET.Element) -> list[PackageFinding]:
    document_tag = f"{{{_WORDPROCESSING_NAMESPACE}}}document"
    body_tag = f"{{{_WORDPROCESSING_NAMESPACE}}}body"
    if root.tag != document_tag or root.find(body_tag) is None:
        return [_finding(PackageErrorCategory.INVALID_WORD_DOCUMENT, "main_document")]
    return []


def validate_docx_package(
    source: bytes | bytearray | memoryview | BinaryIO,
    *,
    limits: PackageValidationLimits = DEFAULT_PACKAGE_LIMITS,
) -> PackageValidationResult:
    """Validate untrusted DOCX bytes without extraction, rendering, logging, or persistence."""
    package, read_finding = _read_package(source, limits)
    if read_finding is not None:
        return _result([read_finding])
    assert package is not None
    if not package.startswith(_ZIP_SIGNATURES):
        return _result([_finding(PackageErrorCategory.NOT_ZIP)])
    raw_directory = _raw_central_directory(package)
    if raw_directory is not None:
        entry_count, has_nul = raw_directory
        if has_nul:
            return _result([_finding(PackageErrorCategory.UNSAFE_ENTRY_NAME, "entry")])
        if entry_count > limits.max_entries:
            return _result([_finding(PackageErrorCategory.ENTRY_COUNT_LIMIT)])
    try:
        with ZipFile(io.BytesIO(package), mode="r", allowZip64=False) as archive:
            findings, normalized_entries = _inspect_entry_metadata(archive.infolist(), limits)
            missing = sorted(_REQUIRED_PARTS.difference(normalized_entries))
            findings.extend(
                _finding(PackageErrorCategory.MISSING_REQUIRED_PART, f"required:{index}")
                for index, _ in enumerate(missing)
            )
            if findings:
                return _result(findings)
            contents, read_findings = _read_entries(archive, normalized_entries, limits)
            findings.extend(read_findings)
    except (BadZipFile, LargeZipFile, OSError, ValueError):
        return _result([_finding(PackageErrorCategory.CORRUPT_ZIP)])

    parsed_xml: dict[str, ET.Element] = {}
    for index, (name, content) in enumerate(contents.items()):
        if dangerous_magic := _dangerous_magic(content):
            findings.append(_finding(dangerous_magic, f"entry:{index}"))
            continue
        if not name.casefold().endswith((".xml", ".rels")):
            continue
        root, finding = _safe_xml(content, location=f"xml:{index}", limits=limits)
        if finding is not None:
            findings.append(finding)
        else:
            assert root is not None
            parsed_xml[name] = root
    if findings:
        return _result(findings)

    findings.extend(_validate_content_types(parsed_xml[_CONTENT_TYPES], normalized_entries))
    findings.extend(_validate_word_document(parsed_xml[_MAIN_DOCUMENT]))
    for name, root in parsed_xml.items():
        if name.endswith(".rels"):
            findings.extend(
                _validate_relationships(root, rels_name=name, entries=normalized_entries)
            )
    return _result(findings)
