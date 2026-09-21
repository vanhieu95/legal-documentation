from __future__ import annotations

import hashlib
import traceback
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4
from zipfile import ZipFile

import pytest
from django.contrib.auth.models import User

from apps.cases.models import CaseRecord
from apps.documents.generation_rendering import (
    GenerationRenderCategory,
    GenerationRenderError,
    _literal_token_allowance,
    _nested_context,
    _shadow_literal_tokens,
    render_reserved_generation,
)
from apps.documents.models import GeneratedDocument, TemplateVersion
from apps.documents.output_validation import InvalidRenderedDocument, inspect_rendered_docx
from apps.documents.registry import ContextMapper, OutputStructureContract, document_registry
from apps.documents.tests.docx_fixtures import minimal_docx, relationships, word_document
from apps.documents.tests.test_template_versions import template_values
from tests.factories import CaseRecordFactory, UserFactory

pytestmark = pytest.mark.django_db


def _template_bytes(**entries: bytes) -> bytes:
    document_xml = word_document(
        (
            ("{{ document.title }}",),
            ("{{ document.notes|default('') }}",),
            ("Page one",),
        )
    ).replace(
        b'<w:p><w:r><w:t xml:space="preserve">Page one</w:t></w:r></w:p>',
        b'<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
        b'<w:tbl><w:tblGrid><w:gridCol w:w="1440"/></w:tblGrid>'
        b"<w:tr><w:tc><w:p><w:r><w:t>Table cell</w:t></w:r></w:p>"
        b"</w:tc></w:tr></w:tbl>",
    )
    styles_xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<w:styles xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main"/>'
    )
    document_relationships = relationships(
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    return minimal_docx(
        entries={
            "word/document.xml": document_xml,
            "word/_rels/document.xml.rels": document_relationships,
            "word/styles.xml": styles_xml,
            **entries,
        }
    )


def _attempt(package: bytes) -> GeneratedDocument:
    actor = cast(User, UserFactory())
    case = cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))
    template = TemplateVersion.objects.create(
        **template_values(
            uploader=actor,
            checksum_sha256=hashlib.sha256(package).hexdigest(),
            byte_size=len(package),
        )
    )
    return GeneratedDocument.objects.create(
        case=case,
        type_key="synthetic-platform-test",
        template_version=template,
        schema_version="v1",
        source_draft_id=uuid4(),
        case_revision=case.revision,
        draft_revision=1,
        input_snapshot={
            "version": 1,
            "values": {
                "title": "Giá trị văn bản",
                "notes": "Ký tự <&> và {{ dữ liệu }}",
                "participant_id": None,
            },
        },
        resolved_values_snapshot={
            "version": 1,
            "values": {"title": "Shared value"},
        },
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
        idempotency_key_hash="a" * 64,
    )


def test_reserved_generation_renders_only_snapshot_context_and_inspects_structure() -> None:
    package = _template_bytes()
    attempt = _attempt(package)

    rendered = render_reserved_generation(attempt=attempt, template_bytes=package)

    assert hashlib.sha256(rendered.content).hexdigest() == rendered.checksum_sha256
    assert rendered.byte_size == len(rendered.content)
    assert rendered.structure.paragraph_count >= 2
    assert rendered.structure.table_count == 1
    assert rendered.structure.section_count == 1
    assert rendered.structure.page_break_count == 1
    assert rendered.structure.has_styles is True
    with ZipFile(BytesIO(rendered.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "Giá trị văn bản" in document_xml
    assert "Shared value" not in document_xml
    assert "Ký tự &lt;&amp;&gt;" in document_xml
    assert "{{ document.title }}" not in document_xml


def test_template_checksum_must_match_the_reserved_identity() -> None:
    package = _template_bytes()
    attempt = _attempt(package)
    tampered = package + b"tampered"

    with pytest.raises(GenerationRenderError) as error:
        render_reserved_generation(attempt=attempt, template_bytes=tampered)

    assert error.value.category is GenerationRenderCategory.INTEGRITY_ERROR
    assert "tampered" not in str(error.value)


def test_template_contract_is_revalidated_immediately_before_rendering() -> None:
    package = _template_bytes()
    attempt = _attempt(package)
    invalid = _template_bytes(
        **{
            "word/header1.xml": word_document((("{{ unknown.value }}",),)),
        }
    )
    attempt.template_version.checksum_sha256 = hashlib.sha256(invalid).hexdigest()
    attempt.template_version.byte_size = len(invalid)
    attempt.template_snapshot["identity"]["checksum_sha256"] = hashlib.sha256(invalid).hexdigest()

    with pytest.raises(GenerationRenderError) as error:
        render_reserved_generation(attempt=attempt, template_bytes=invalid)

    assert error.value.category is GenerationRenderCategory.TEMPLATE_INVALID


def test_missing_or_unknown_mapper_context_fails_before_docxtpl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _template_bytes()
    attempt = _attempt(package)
    registration = document_registry.get("synthetic-platform-test")
    invalid_registration = replace(
        registration,
        context_mapper=lambda _values: {"document.unknown": "value"},
    )
    monkeypatch.setattr(
        "apps.documents.generation_rendering.document_registry",
        SimpleNamespace(get=lambda _key: invalid_registration),
    )

    with pytest.raises(GenerationRenderError) as error:
        render_reserved_generation(attempt=attempt, template_bytes=package)

    assert error.value.category is GenerationRenderCategory.CONTEXT_MISSING


def test_declared_post_processor_runs_and_temporary_files_are_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _template_bytes()
    attempt = _attempt(package)
    process_root = tmp_path / "process"
    process_root.mkdir()
    called: list[Path] = []
    registration = replace(
        document_registry.get("synthetic-platform-test"),
        post_processor_name="approved_processor",
    )
    registry = SimpleNamespace(
        get=lambda _key: registration,
        get_post_processor=lambda _name: lambda path: called.append(Path(path)),
    )
    monkeypatch.setattr("apps.documents.generation_rendering.document_registry", registry)
    monkeypatch.setattr("apps.documents.generation_rendering.tempfile.tempdir", str(process_root))

    render_reserved_generation(attempt=attempt, template_bytes=package)

    assert len(called) == 1
    assert called[0].name == "rendered.docx"
    assert list(process_root.iterdir()) == []


def test_render_failure_is_safe_and_cleans_temporary_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _template_bytes()
    attempt = _attempt(package)
    process_root = tmp_path / "process"
    process_root.mkdir()
    monkeypatch.setattr("apps.documents.generation_rendering.tempfile.tempdir", str(process_root))

    def fail_save(_self: object, _path: str) -> None:
        raise OSError("synthetic sensitive render path")

    monkeypatch.setattr("apps.documents.generation_rendering.DocxTemplate.save", fail_save)

    with pytest.raises(GenerationRenderError) as error:
        render_reserved_generation(attempt=attempt, template_bytes=package)

    assert error.value.category is GenerationRenderCategory.RENDER_ERROR
    assert "sensitive" not in str(error.value)
    assert "sensitive" not in "".join(traceback.format_exception(error.value))
    assert error.value.__cause__ is None
    assert list(process_root.iterdir()) == []


def test_malformed_rendered_output_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _template_bytes()
    attempt = _attempt(package)

    def corrupt_output(_self: object, path: str) -> None:
        Path(path).write_bytes(b"not a docx")

    monkeypatch.setattr("apps.documents.generation_rendering.DocxTemplate.save", corrupt_output)

    with pytest.raises(GenerationRenderError) as error:
        render_reserved_generation(attempt=attempt, template_bytes=package)

    assert error.value.category is GenerationRenderCategory.INTEGRITY_ERROR


def test_rendered_package_with_unresolved_source_token_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _template_bytes()
    attempt = _attempt(package)

    def unresolved_output(_self: object, path: str) -> None:
        Path(path).write_bytes(
            minimal_docx(entries={"word/document.xml": word_document((("{{ unresolved }}",),))})
        )

    monkeypatch.setattr("apps.documents.generation_rendering.DocxTemplate.save", unresolved_output)

    with pytest.raises(GenerationRenderError) as error:
        render_reserved_generation(attempt=attempt, template_bytes=package)

    assert error.value.category is GenerationRenderCategory.INTEGRITY_ERROR


def test_snapshot_values_must_remain_mapping_payloads() -> None:
    package = _template_bytes()
    attempt = _attempt(package)
    attempt.input_snapshot = {"version": 1, "values": []}

    with pytest.raises(GenerationRenderError) as error:
        render_reserved_generation(attempt=attempt, template_bytes=package)

    assert error.value.category is GenerationRenderCategory.CONTEXT_MISSING


@pytest.mark.parametrize(
    "mapper",
    [
        lambda _values: (_ for _ in ()).throw(ValueError("private mapper detail")),
        lambda _values: "not a mapping",
        lambda _values: {"document.title": 7},
    ],
)
def test_mapper_exceptions_and_invalid_shapes_are_bounded(
    mapper: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _template_bytes()
    attempt = _attempt(package)
    registration = replace(
        document_registry.get("synthetic-platform-test"),
        context_mapper=cast(ContextMapper, mapper),
    )
    monkeypatch.setattr(
        "apps.documents.generation_rendering.document_registry",
        SimpleNamespace(get=lambda _key: registration),
    )

    with pytest.raises(GenerationRenderError) as error:
        render_reserved_generation(attempt=attempt, template_bytes=package)

    assert error.value.category is GenerationRenderCategory.CONTEXT_MISSING
    assert "private" not in str(error.value)


def test_unknown_or_disabled_registration_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _template_bytes()
    attempt = _attempt(package)
    registration = replace(
        document_registry.get("synthetic-platform-test"),
        enabled=False,
    )
    monkeypatch.setattr(
        "apps.documents.generation_rendering.document_registry",
        SimpleNamespace(get=lambda _key: registration),
    )

    with pytest.raises(GenerationRenderError) as error:
        render_reserved_generation(attempt=attempt, template_bytes=package)

    assert error.value.category is GenerationRenderCategory.TEMPLATE_INVALID


def test_nested_context_rejects_conflicting_paths_and_literal_tokens_are_shadowed() -> None:
    with pytest.raises(GenerationRenderError) as error:
        _nested_context({"document.title": "title", "document.title.value": "conflict"})

    assert error.value.category is GenerationRenderCategory.CONTEXT_MISSING
    original = {"rows": ["one {{ token }}", {"value": "{% action %}"}], "count": 2}
    shadow = _shadow_literal_tokens(
        original,
    )
    assert "{{ token }}" not in str(shadow)
    assert "{% action %}" not in str(shadow)
    assert shadow == {
        "rows": ["one 00000000000", {"value": "000000000000"}],
        "count": 2,
    }
    shadow_rows = cast(dict[str, list[object]], shadow)["rows"]
    original_rows = cast(list[object], original["rows"])
    assert len(cast(str, shadow_rows[0])) == len(cast(str, original_rows[0]))


def test_output_inspection_covers_supported_text_parts() -> None:
    header = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<w:hdr xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main"><w:p><w:r><w:t>Header</w:t></w:r></w:p></w:hdr>'
    )
    footer = header.replace(b"w:hdr", b"w:ftr").replace(b"Header", b"Footer")
    package = _template_bytes(
        **{
            "word/document.xml": word_document((("Rendered",),)),
            "word/header1.xml": header,
            "word/footer1.xml": footer,
        }
    )

    structure = inspect_rendered_docx(package, template_bytes=package)

    assert structure.header_count == 1
    assert structure.footer_count == 1
    assert {"word/header1.xml", "word/footer1.xml"}.issubset(structure.text_parts)


@pytest.mark.parametrize(
    ("rendered", "template"),
    [
        (b"", b""),
        (_template_bytes(), b"not a template zip"),
        (
            minimal_docx(
                entries={
                    "word/document.xml": (
                        b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
                        b'wordprocessingml/2006/main"><w:body/></w:document>'
                    )
                }
            ),
            minimal_docx(
                entries={
                    "word/document.xml": (
                        b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
                        b'wordprocessingml/2006/main"><w:body/></w:document>'
                    )
                }
            ),
        ),
        (
            minimal_docx(entries={"word/document.xml": word_document((("unfinished {{",),))}),
            minimal_docx(entries={"word/document.xml": word_document((("unfinished {{",),))}),
        ),
    ],
)
def test_output_inspection_rejects_invalid_size_zip_structure_and_delimiters(
    rendered: bytes,
    template: bytes,
) -> None:
    with pytest.raises(InvalidRenderedDocument):
        inspect_rendered_docx(rendered, template_bytes=template)


def test_output_inspection_rejects_a_lost_protected_part() -> None:
    with pytest.raises(InvalidRenderedDocument):
        inspect_rendered_docx(minimal_docx(), template_bytes=_template_bytes())


def test_output_inspection_rejects_lost_tables_sections_or_page_breaks() -> None:
    template = _template_bytes()
    rendered = _template_bytes(
        **{"word/document.xml": word_document((("Rendered without important structure",),))}
    )

    with pytest.raises(InvalidRenderedDocument):
        inspect_rendered_docx(
            rendered,
            template_bytes=template,
            structure_contract=document_registry.get(
                "synthetic-platform-test"
            ).output_structure_contract,
        )


def test_output_structure_contract_does_not_require_optional_source_structures() -> None:
    template = _template_bytes()
    rendered = _template_bytes(
        **{"word/document.xml": word_document((("Valid optional-empty branch",),))}
    )

    structure = inspect_rendered_docx(rendered, template_bytes=template)

    assert structure.table_count == 0
    assert structure.page_break_count == 0


def test_conditional_source_structure_uses_the_registered_output_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conditional_xml = word_document(
        (
            ("{%p if document.notes|default('') %}",),
            ("Conditional break",),
            ("{%p endif %}",),
            ("{{ document.title }}",),
        )
    ).replace(
        b'<w:p><w:r><w:t xml:space="preserve">Conditional break</w:t></w:r></w:p>',
        b'<w:p><w:r><w:br w:type="page"/></w:r></w:p>',
    )
    package = _template_bytes(**{"word/document.xml": conditional_xml})
    attempt = _attempt(package)
    attempt.input_snapshot["values"]["notes"] = ""
    registration = replace(
        document_registry.get("synthetic-platform-test"),
        output_structure_contract=OutputStructureContract(),
    )
    monkeypatch.setattr(
        "apps.documents.generation_rendering.document_registry",
        SimpleNamespace(get=lambda _key: registration),
    )

    rendered = render_reserved_generation(attempt=attempt, template_bytes=package)

    assert rendered.structure.page_break_count == 0


def test_literal_value_may_exactly_match_a_source_placeholder() -> None:
    template = _template_bytes()
    attempt = _attempt(template)
    attempt.input_snapshot["values"]["notes"] = "{{ document.title }}"

    rendered = render_reserved_generation(attempt=attempt, template_bytes=template)

    with ZipFile(BytesIO(rendered.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "Giá trị văn bản" in document_xml
    assert document_xml.count("{{ document.title }}") == 1


def test_unresolved_tokens_in_xml_attributes_are_rejected() -> None:
    template_xml = word_document((("Rendered",),))
    rendered_xml = template_xml.replace(b"<w:p>", b'<w:p data-check="{{ unresolved }}">', 1)
    template = _template_bytes(**{"word/document.xml": template_xml})
    rendered = _template_bytes(**{"word/document.xml": rendered_xml})

    with pytest.raises(InvalidRenderedDocument):
        inspect_rendered_docx(rendered, template_bytes=template)


def test_unused_literal_tokens_cannot_allowlist_injected_output() -> None:
    template_xml = word_document((("Rendered",),))
    rendered_xml = template_xml.replace(b"<w:p>", b'<w:p data-check="{{ injected }}">', 1)
    template = _template_bytes(**{"word/document.xml": template_xml})
    rendered = _template_bytes(**{"word/document.xml": rendered_xml})
    provenance = _literal_token_allowance(rendered, rendered)

    assert provenance == {}
    with pytest.raises(InvalidRenderedDocument):
        inspect_rendered_docx(
            rendered,
            template_bytes=template,
            literal_tokens_by_part=provenance,
        )


@pytest.mark.parametrize(
    ("filter_name", "input_value", "expected"),
    [
        ("lower", "AA {{ MiXeD }} BB", "aa {{ mixed }} bb"),
        ("upper", "aa {{ MiXeD }} bb", "AA {{ MIXED }} BB"),
        ("length", "AA {{ MiXeD }} BB", "17"),
    ],
)
def test_literal_token_provenance_preserves_filter_semantics(
    filter_name: str,
    input_value: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _template_bytes()
    with ZipFile(BytesIO(base)) as archive:
        document_xml = archive.read("word/document.xml")
    package = _template_bytes(
        **{
            "word/document.xml": document_xml.replace(
                b"{{ document.notes|default('') }}",
                f"{{{{ document.notes|{filter_name} }}}}".encode(),
            )
        }
    )
    attempt = _attempt(package)
    attempt.input_snapshot["values"]["notes"] = input_value
    registration = document_registry.get("synthetic-platform-test")
    contract = replace(
        registration.placeholder_contract,
        allowed_filters=registration.placeholder_contract.allowed_filters | {filter_name},
    )
    monkeypatch.setattr(
        "apps.documents.generation_rendering.document_registry",
        SimpleNamespace(get=lambda _key: replace(registration, placeholder_contract=contract)),
    )

    rendered = render_reserved_generation(attempt=attempt, template_bytes=package)

    with ZipFile(BytesIO(rendered.content)) as archive:
        output_xml = archive.read("word/document.xml").decode("utf-8")
    assert expected in output_xml


def test_literal_tokens_with_xml_metacharacters_remain_well_formed() -> None:
    package = _template_bytes()
    attempt = _attempt(package)
    attempt.input_snapshot["values"]["notes"] = "prefix {{ <&> }} suffix"

    rendered = render_reserved_generation(attempt=attempt, template_bytes=package)

    with ZipFile(BytesIO(rendered.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "prefix {{ &lt;&amp;&gt; }} suffix" in document_xml


@pytest.mark.parametrize("input_value", ["literal {{ text", "100% }}", "{%"])
def test_unmatched_jinja_delimiters_in_user_values_remain_literal(input_value: str) -> None:
    package = _template_bytes()
    attempt = _attempt(package)
    attempt.input_snapshot["values"]["notes"] = input_value

    rendered = render_reserved_generation(attempt=attempt, template_bytes=package)

    with ZipFile(BytesIO(rendered.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert input_value in document_xml
