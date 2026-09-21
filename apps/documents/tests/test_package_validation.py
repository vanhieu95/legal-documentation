from __future__ import annotations

import logging
import math
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from zipfile import ZipFile

import pytest

from apps.documents.limits import DEFAULT_PACKAGE_LIMITS
from apps.documents.package_validation import (
    PackageErrorCategory,
    PackageValidationLimits,
    validate_docx_package,
)
from apps.documents.tests.docx_fixtures import (
    CONTENT_TYPES,
    DOCUMENT_RELS,
    ROOT_RELS,
    mark_first_entry_encrypted,
    minimal_docx,
    relationships,
    replace_raw_entry_name,
    stored_docx,
    word_document,
)


def categories(
    package: bytes | BinaryIO,
    *,
    limits: PackageValidationLimits = DEFAULT_PACKAGE_LIMITS,
) -> tuple[PackageErrorCategory, ...]:
    return tuple(
        finding.category for finding in validate_docx_package(package, limits=limits).findings
    )


def test_minimal_synthetic_docx_is_valid_and_deterministic() -> None:
    package = minimal_docx()

    first = validate_docx_package(package)
    second = validate_docx_package(BytesIO(package))

    assert first.is_valid is True
    assert first.findings == ()
    assert second == first


@pytest.mark.parametrize(
    ("package", "category"),
    [
        (b"renamed non-zip synthetic content", PackageErrorCategory.NOT_ZIP),
        (minimal_docx()[:-12], PackageErrorCategory.CORRUPT_ZIP),
        (
            minimal_docx(entries={"word/document.xml": b"<not-valid"}),
            PackageErrorCategory.MALFORMED_XML,
        ),
        (
            minimal_docx(extra_entries=(("../outside.xml", b"<safe/>"),)),
            PackageErrorCategory.UNSAFE_ENTRY_NAME,
        ),
    ],
)
def test_hostile_packages_fail_with_stable_categories(
    package: bytes, category: PackageErrorCategory
) -> None:
    result = validate_docx_package(package)

    assert result.is_valid is False
    assert category in tuple(finding.category for finding in result.findings)
    assert all(len(finding.location) <= 160 for finding in result.findings)


def test_compressed_upload_limit_is_enforced_at_the_exact_boundary() -> None:
    package = minimal_docx()

    assert validate_docx_package(
        package, limits=PackageValidationLimits(max_compressed_bytes=len(package))
    ).is_valid
    assert validate_docx_package(
        package, limits=PackageValidationLimits(max_compressed_bytes=len(package) + 1)
    ).is_valid
    assert PackageErrorCategory.COMPRESSED_SIZE_LIMIT in categories(
        package,
        limits=PackageValidationLimits(max_compressed_bytes=len(package) - 1),
    )


@pytest.mark.parametrize(
    "missing_name",
    [
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
    ],
)
def test_each_required_opc_part_is_required(missing_name: str) -> None:
    assert PackageErrorCategory.MISSING_REQUIRED_PART in categories(
        minimal_docx(omit_names=frozenset({missing_name}))
    )


@pytest.mark.parametrize(
    "name",
    [
        "/absolute.xml",
        "../traversal.xml",
        "word/../traversal.xml",
        r"word\..\traversal.xml",
        "word/%2e%2e/traversal.xml",
        "word/%252e%252e/traversal.xml",
        "word/unsafe?.xml",
        "C:/absolute.xml",
    ],
)
def test_normalized_unsafe_entry_names_are_rejected(name: str) -> None:
    assert PackageErrorCategory.UNSAFE_ENTRY_NAME in categories(
        minimal_docx(extra_entries=((name, b"<safe/>"),))
    )


def test_nul_in_raw_central_directory_name_is_rejected() -> None:
    package = minimal_docx(extra_entries=(("word/unsafeQ.xml", b"<safe/>"),))
    hostile = replace_raw_entry_name(package, b"word/unsafeQ.xml", b"word/unsafe\x00.xml")

    assert PackageErrorCategory.UNSAFE_ENTRY_NAME in categories(hostile)


def test_traversal_is_decoded_until_stable() -> None:
    encoded_parent = ".."
    for _ in range(12):
        encoded_parent = encoded_parent.replace("%", "%25").replace(".", "%2e")
    hostile_name = f"word/{encoded_parent}/payload.xml"

    assert PackageErrorCategory.UNSAFE_ENTRY_NAME in categories(
        minimal_docx(extra_entries=((hostile_name, b"<safe/>"),))
    )


def test_duplicate_and_case_colliding_entries_are_rejected() -> None:
    with pytest.warns(UserWarning, match="Duplicate name"):
        duplicate = minimal_docx(extra_entries=(("word/document.xml", b"<duplicate/>"),))
    case_collision = minimal_docx(extra_entries=(("WORD/document.xml", b"<collision/>"),))

    assert PackageErrorCategory.DUPLICATE_ENTRY in categories(duplicate)
    assert PackageErrorCategory.CASE_COLLISION in categories(case_collision)


def test_entry_count_limit_allows_exact_limit_and_rejects_above() -> None:
    package = minimal_docx()

    assert validate_docx_package(package, limits=PackageValidationLimits(max_entries=4)).is_valid
    assert PackageErrorCategory.ENTRY_COUNT_LIMIT in categories(
        package, limits=PackageValidationLimits(max_entries=3)
    )


def test_excessive_entry_count_is_rejected_before_zipfile_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = minimal_docx(
        extra_entries=((f"word/item{index}.xml", b"<item/>") for index in range(20))
    )

    def fail_if_opened(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ZipFile must not open a package over the entry-count limit")

    monkeypatch.setattr("apps.documents.package_validation.ZipFile", fail_if_opened)

    assert categories(package, limits=PackageValidationLimits(max_entries=10)) == (
        PackageErrorCategory.ENTRY_COUNT_LIMIT,
    )


def test_uncompressed_size_limits_allow_exact_boundaries_and_reject_below() -> None:
    package = stored_docx()
    with ZipFile(BytesIO(package)) as archive:
        sizes = [entry.file_size for entry in archive.infolist()]
    largest = max(sizes)
    total = sum(sizes)

    assert validate_docx_package(
        package,
        limits=PackageValidationLimits(
            max_entry_uncompressed_bytes=largest,
            max_total_uncompressed_bytes=total,
            max_compression_ratio=1.0,
        ),
    ).is_valid
    assert validate_docx_package(
        package,
        limits=PackageValidationLimits(
            max_entry_uncompressed_bytes=largest + 1,
            max_total_uncompressed_bytes=total + 1,
            max_compression_ratio=1.01,
        ),
    ).is_valid
    assert PackageErrorCategory.ENTRY_SIZE_LIMIT in categories(
        package, limits=PackageValidationLimits(max_entry_uncompressed_bytes=largest - 1)
    )
    assert PackageErrorCategory.TOTAL_SIZE_LIMIT in categories(
        package, limits=PackageValidationLimits(max_total_uncompressed_bytes=total - 1)
    )
    assert PackageErrorCategory.COMPRESSION_RATIO_LIMIT in categories(
        package, limits=PackageValidationLimits(max_compression_ratio=0.99)
    )


def test_xml_size_and_depth_limits_are_exact() -> None:
    document = word_document()
    package = minimal_docx(entries={"word/document.xml": document})
    maximum_xml_size = max(len(CONTENT_TYPES), len(ROOT_RELS), len(DOCUMENT_RELS), len(document))
    assert validate_docx_package(
        package, limits=PackageValidationLimits(max_xml_bytes=maximum_xml_size)
    ).is_valid
    assert PackageErrorCategory.XML_SIZE_LIMIT in categories(
        package, limits=PackageValidationLimits(max_xml_bytes=maximum_xml_size - 1)
    )

    nested = b'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>x</w:t></w:r></w:p></w:body></w:document>'
    nested_package = minimal_docx(entries={"word/document.xml": nested})
    assert validate_docx_package(
        nested_package, limits=PackageValidationLimits(max_xml_depth=4)
    ).is_valid
    assert PackageErrorCategory.XML_DEPTH_LIMIT in categories(
        nested_package, limits=PackageValidationLimits(max_xml_depth=3)
    )


def test_xml_depth_is_rejected_before_element_tree_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = (
        b'<?xml version="1.0"?>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main"><w:body><w:p/></w:body></w:document>'
    )
    package = minimal_docx(entries={"word/document.xml": nested})

    original_fromstring = __import__("xml.etree.ElementTree", fromlist=["fromstring"]).fromstring

    def fail_if_built(content: bytes) -> object:
        if content == nested:
            raise AssertionError("unsafe XML must fail before tree construction")
        return original_fromstring(content)

    monkeypatch.setattr("apps.documents.package_validation.ET.fromstring", fail_if_built)

    assert PackageErrorCategory.XML_DEPTH_LIMIT in categories(
        package, limits=PackageValidationLimits(max_xml_depth=1)
    )


def test_encrypted_entry_is_rejected_before_decryption() -> None:
    assert PackageErrorCategory.ENCRYPTED_ENTRY in categories(
        mark_first_entry_encrypted(minimal_docx())
    )


@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("word/vbaProject.bin", PackageErrorCategory.MACRO_CONTENT),
        ("word/activeX/activeX1.xml", PackageErrorCategory.ACTIVEX_CONTENT),
        ("word/embeddings/oleObject1.bin", PackageErrorCategory.OLE_CONTENT),
        ("word/embeddings/package1.zip", PackageErrorCategory.EMBEDDED_CONTENT),
        ("word/media/payload.exe", PackageErrorCategory.EXECUTABLE_CONTENT),
        ("word/font.bin", PackageErrorCategory.PROHIBITED_BINARY),
        ("custom/payload.xml", PackageErrorCategory.UNSUPPORTED_STRUCTURE),
    ],
)
def test_active_embedded_binary_and_unsupported_content_is_rejected(
    name: str, category: PackageErrorCategory
) -> None:
    assert category in categories(minimal_docx(extra_entries=((name, b"synthetic"),)))


@pytest.mark.parametrize(
    ("content", "category"),
    [
        (b"MZ" + b"\x00" * 32, PackageErrorCategory.EXECUTABLE_CONTENT),
        (b"\x7fELF" + b"\x00" * 32, PackageErrorCategory.EXECUTABLE_CONTENT),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", PackageErrorCategory.OLE_CONTENT),
        (b"PK\x03\x04" + b"\x00" * 32, PackageErrorCategory.EMBEDDED_CONTENT),
    ],
)
def test_dangerous_magic_cannot_hide_behind_an_image_name(
    content: bytes, category: PackageErrorCategory
) -> None:
    content_types = CONTENT_TYPES.replace(
        b"</Types>", b'<Default Extension="png" ContentType="image/png"/></Types>'
    )
    package = minimal_docx(
        entries={"[Content_Types].xml": content_types},
        extra_entries=(("word/media/image.png", content),),
    )

    assert category in categories(package)


def test_macro_enabled_main_content_type_is_rejected() -> None:
    macro_content_types = CONTENT_TYPES.replace(
        b"wordprocessingml.document.main+xml", b"wordprocessingml.document.macroEnabled.main+xml"
    )
    assert PackageErrorCategory.MACRO_CONTENT in categories(
        minimal_docx(entries={"[Content_Types].xml": macro_content_types})
    )


@pytest.mark.parametrize(
    ("content_type", "category"),
    [
        ("application/vnd.ms-office.activeX+xml", PackageErrorCategory.ACTIVEX_CONTENT),
        (
            "application/vnd.openxmlformats-officedocument.oleObject",
            PackageErrorCategory.OLE_CONTENT,
        ),
        (
            "application/vnd.openxmlformats-officedocument.package",
            PackageErrorCategory.EMBEDDED_CONTENT,
        ),
        ("application/x-msdownload", PackageErrorCategory.EXECUTABLE_CONTENT),
    ],
)
def test_prohibited_content_type_declarations_are_rejected(
    content_type: str, category: PackageErrorCategory
) -> None:
    declaration = (
        f'<Override PartName="/word/missing.xml" ContentType="{content_type}"/>'
    ).encode()
    content_types = CONTENT_TYPES.replace(b"</Types>", declaration + b"</Types>")

    result_categories = categories(minimal_docx(entries={"[Content_Types].xml": content_types}))

    assert category in result_categories
    assert PackageErrorCategory.INVALID_CONTENT_TYPES in result_categories


def test_content_type_defaults_and_root_document_relationship_are_required() -> None:
    missing_default = CONTENT_TYPES.replace(
        b'<Default Extension="xml" ContentType="application/xml"/>', b""
    )
    empty_root_relationships = relationships()

    assert PackageErrorCategory.INVALID_CONTENT_TYPES in categories(
        minimal_docx(entries={"[Content_Types].xml": missing_default})
    )
    assert PackageErrorCategory.MALFORMED_RELATIONSHIPS in categories(
        minimal_docx(entries={"_rels/.rels": empty_root_relationships})
    )


def test_content_type_declarations_are_unique_known_and_cover_every_part() -> None:
    duplicate_default = CONTENT_TYPES.replace(
        b"</Types>", b'<Default Extension="xml" ContentType="application/xml"/></Types>'
    )
    unknown_child = CONTENT_TYPES.replace(b"</Types>", b"<Unexpected/></Types>")
    uncovered_image = minimal_docx(
        extra_entries=(("word/media/image.png", b"\x89PNG\r\n\x1a\nsynthetic"),)
    )

    assert PackageErrorCategory.INVALID_CONTENT_TYPES in categories(
        minimal_docx(entries={"[Content_Types].xml": duplicate_default})
    )
    assert PackageErrorCategory.INVALID_CONTENT_TYPES in categories(
        minimal_docx(entries={"[Content_Types].xml": unknown_child})
    )
    assert PackageErrorCategory.INVALID_CONTENT_TYPES in categories(uncovered_image)


def test_internal_relationship_must_be_safe_and_resolve_to_an_entry() -> None:
    internal = relationships(
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    valid = minimal_docx(
        entries={
            "word/_rels/document.xml.rels": internal,
            "word/styles.xml": b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>',
        }
    )
    missing = minimal_docx(entries={"word/_rels/document.xml.rels": internal})

    assert validate_docx_package(valid).is_valid
    assert PackageErrorCategory.MISSING_RELATIONSHIP_TARGET in categories(missing)


@pytest.mark.parametrize(
    "relationship_xml",
    [
        "<Unexpected/>",
        '<Relationship Id="rId2" Type="synthetic"/>',
    ],
)
def test_relationship_children_require_the_expected_shape(relationship_xml: str) -> None:
    assert PackageErrorCategory.MALFORMED_RELATIONSHIPS in categories(
        minimal_docx(
            entries={
                "word/_rels/document.xml.rels": relationships(relationship_xml),
            }
        )
    )


@pytest.mark.parametrize(
    "relationship_xml",
    [
        '<Relationship Type="synthetic" Target="styles.xml"/>',
        '<Relationship Id="rId2" Target="styles.xml"/>',
        '<Relationship Id="rId2" Type="synthetic" Target="styles.xml"/>',
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/attachedTemplate" Target="styles.xml"/>',
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/styles" Target="styles.xml" TargetMode="Other"/>',
    ],
)
def test_relationships_require_unique_ids_safe_types_and_target_mode(
    relationship_xml: str,
) -> None:
    package = minimal_docx(
        entries={
            "word/_rels/document.xml.rels": relationships(relationship_xml),
            "word/styles.xml": b'<w:styles xmlns:w="http://schemas.openxmlformats.org/'
            b'wordprocessingml/2006/main"/>',
        }
    )

    assert PackageErrorCategory.MALFORMED_RELATIONSHIPS in categories(package)


@pytest.mark.parametrize(
    ("target", "target_mode", "category"),
    [
        (
            "https://example.invalid/resource",
            "External",
            PackageErrorCategory.EXTERNAL_RELATIONSHIP,
        ),
        ("file:///private/resource", "External", PackageErrorCategory.EXTERNAL_RELATIONSHIP),
        ("../outside.xml", "Internal", PackageErrorCategory.UNSAFE_RELATIONSHIP_TARGET),
        (r"..\outside.xml", "Internal", PackageErrorCategory.UNSAFE_RELATIONSHIP_TARGET),
        ("%2e%2e/outside.xml", "Internal", PackageErrorCategory.UNSAFE_RELATIONSHIP_TARGET),
        (
            "https://example.invalid/resource",
            "Internal",
            PackageErrorCategory.UNSAFE_RELATIONSHIP_TARGET,
        ),
    ],
)
def test_external_and_unsafe_internal_relationships_are_rejected(
    target: str, target_mode: str, category: PackageErrorCategory
) -> None:
    document_rels = relationships(
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/styles" Target="{target}" '
        f'TargetMode="{target_mode}"/>'
    )
    assert category in categories(
        minimal_docx(entries={"word/_rels/document.xml.rels": document_rels})
    )


@pytest.mark.parametrize(
    ("name", "content", "category"),
    [
        ("[Content_Types].xml", b"<Types", PackageErrorCategory.MALFORMED_XML),
        (
            "[Content_Types].xml",
            b'<Types xmlns="unexpected"/>',
            PackageErrorCategory.INVALID_CONTENT_TYPES,
        ),
        ("word/_rels/document.xml.rels", b"<Relationships", PackageErrorCategory.MALFORMED_XML),
        (
            "word/_rels/document.xml.rels",
            b'<Relationships xmlns="unexpected"/>',
            PackageErrorCategory.MALFORMED_RELATIONSHIPS,
        ),
        (
            "word/document.xml",
            b'<!DOCTYPE x [<!ENTITY leak SYSTEM "file:///etc/passwd">]><x>&leak;</x>',
            PackageErrorCategory.XML_DTD_PROHIBITED,
        ),
        (
            "word/document.xml",
            b'<!DOCTYPE x [<!ENTITY network SYSTEM "https://example.invalid/">]><x>&network;</x>',
            PackageErrorCategory.XML_DTD_PROHIBITED,
        ),
    ],
)
def test_malformed_or_entity_based_xml_is_rejected(
    name: str, content: bytes, category: PackageErrorCategory
) -> None:
    assert category in categories(minimal_docx(entries={name: content}))


def test_utf16_dtd_and_entity_declarations_are_rejected() -> None:
    xml = '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE x [<!ENTITY x "expanded">]><x>&x;</x>'

    assert PackageErrorCategory.XML_DTD_PROHIBITED in categories(
        minimal_docx(entries={"word/document.xml": xml.encode("utf-16")})
    )


@pytest.mark.parametrize("encoding", ["utf-32", "utf-16-be", "utf-16-le"])
def test_dtd_scan_covers_supported_wide_xml_encodings(encoding: str) -> None:
    xml = '<?xml version="1.0"?><!DOCTYPE x><x/>'

    assert PackageErrorCategory.XML_DTD_PROHIBITED in categories(
        minimal_docx(entries={"word/document.xml": xml.encode(encoding)})
    )


def test_invalid_xml_encoding_is_rejected_without_parser_details() -> None:
    assert PackageErrorCategory.MALFORMED_XML in categories(
        minimal_docx(entries={"word/document.xml": b"\xff\xfe\xff"})
    )


@pytest.mark.parametrize(
    "document",
    [
        b"<x/>",
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>',
    ],
)
def test_main_part_must_be_a_wordprocessingml_document_with_a_body(document: bytes) -> None:
    assert PackageErrorCategory.INVALID_WORD_DOCUMENT in categories(
        minimal_docx(entries={"word/document.xml": document})
    )


def test_document_relationship_part_is_optional_without_outgoing_relationships() -> None:
    package = minimal_docx(omit_names=frozenset({"word/_rels/document.xml.rels"}))

    assert validate_docx_package(package).is_valid


class InterruptedStream:
    def read(self, _size: int) -> bytes:
        raise OSError("synthetic sensitive content must not escape")


def test_interrupted_stream_returns_a_safe_bounded_result() -> None:
    result = validate_docx_package(InterruptedStream())  # type: ignore[arg-type]

    assert result.findings == (
        result.findings[0].__class__(PackageErrorCategory.INTERRUPTED_READ, "package"),
    )
    assert "sensitive" not in repr(result)


class NonBytesStream:
    def read(self, _size: int) -> str:
        return "not bytes"


class OversizedChunkStream:
    def read(self, size: int) -> bytes:
        return b"P" * (size + 1)


def test_stream_must_return_bytes_and_is_bounded_incrementally() -> None:
    assert categories(NonBytesStream()) == (  # type: ignore[arg-type]
        PackageErrorCategory.INTERRUPTED_READ,
    )
    assert categories(
        BytesIO(b"P" * 5), limits=PackageValidationLimits(max_compressed_bytes=4)
    ) == (PackageErrorCategory.COMPRESSED_SIZE_LIMIT,)
    assert categories(OversizedChunkStream()) == (  # type: ignore[arg-type]
        PackageErrorCategory.COMPRESSED_SIZE_LIMIT,
    )


class BrokenStream:
    def read(self, _size: int) -> bytes:
        raise TypeError("synthetic stream failure")


def test_ordinary_stream_failures_remain_inside_the_safe_result_boundary() -> None:
    assert categories(BrokenStream()) == (  # type: ignore[arg-type]
        PackageErrorCategory.INTERRUPTED_READ,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"max_compressed_bytes": 0},
        {"max_entries": -1},
        {"max_total_uncompressed_bytes": 0},
        {"max_entry_uncompressed_bytes": 0},
        {"max_compression_ratio": math.nan},
        {"max_compression_ratio": math.inf},
        {"max_xml_bytes": 0},
        {"max_xml_depth": -1},
    ],
)
def test_limits_cannot_be_constructed_with_fail_open_values(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        PackageValidationLimits(**changes)  # type: ignore[arg-type]


def test_findings_are_bounded_even_for_many_independent_failures() -> None:
    package = minimal_docx(
        extra_entries=((f"unsupported-{index}.dat", b"x") for index in range(100))
    )

    result = validate_docx_package(package)

    assert 1 <= len(result.findings) <= 50


def test_safe_binary_media_and_document_properties_are_allowed() -> None:
    content_types = CONTENT_TYPES.replace(
        b"</Types>",
        b'<Default Extension="png" ContentType="image/png"/>'
        b'<Default Extension="odttf" '
        b'ContentType="application/vnd.ms-package.obfuscated-opentype"/>'
        b"</Types>",
    )
    package = minimal_docx(
        entries={"[Content_Types].xml": content_types},
        extra_entries=(
            ("word/media/image1.png", b"synthetic image"),
            ("word/fonts/font1.odttf", b"synthetic font"),
            ("docProps/core.xml", b"<properties/>"),
        ),
    )

    assert validate_docx_package(package).is_valid


def test_failures_create_no_temporary_resources_or_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    marker = tmp_path / "preexisting"
    marker.write_text("synthetic marker")
    caplog.set_level(logging.DEBUG)

    result = validate_docx_package(
        minimal_docx(extra_entries=(("../sensitive-client-name.xml", b"private fixture text"),))
    )

    assert result.is_valid is False
    assert tuple(tmp_path.iterdir()) == (marker,)
    assert caplog.records == []
    report = repr(result)
    assert "sensitive-client-name" not in report
    assert "private fixture text" not in report
