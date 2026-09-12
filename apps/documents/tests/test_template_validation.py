from __future__ import annotations

import logging
from dataclasses import replace
from unittest.mock import patch

import pytest
from jinja2 import Environment, StrictUndefined, UndefinedError
from jinja2.exceptions import SecurityError
from markupsafe import Markup

from apps.documents.limits import DEFAULT_TEMPLATE_LIMITS, TemplateValidationLimits
from apps.documents.registry import (
    DocumentRegistration,
    PlaceholderContract,
    PlaceholderDefinition,
    PlaceholderValueKind,
    document_registry,
)
from apps.documents.template_validation import (
    SUPPORTED_TEXT_PARTS,
    TemplateErrorCategory,
    create_restricted_environment,
    validate_template,
)
from apps.documents.tests.docx_fixtures import minimal_docx, stored_docx, word_document

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _registration(
    *,
    required: tuple[PlaceholderDefinition, ...] | None = None,
    optional: tuple[PlaceholderDefinition, ...] | None = None,
    filters: frozenset[str] = frozenset(),
    globals_: frozenset[str] = frozenset(),
) -> DocumentRegistration:
    existing = document_registry.get("synthetic-platform-test")
    contract = PlaceholderContract(
        required=required or existing.placeholder_contract.required,
        optional=(existing.placeholder_contract.optional if optional is None else optional),
        allowed_filters=filters,
        allowed_globals=globals_,
    )
    return replace(existing, placeholder_contract=contract)


def _categories(
    package: bytes, *, registration: DocumentRegistration | None = None
) -> tuple[TemplateErrorCategory, ...]:
    result = validate_template(package, registration or _registration())
    return tuple(finding.category for finding in result.findings)


def _part(root: str, paragraphs: tuple[tuple[str, ...], ...]) -> bytes:
    content = "".join(
        "<w:p>" + "".join(f"<w:r><w:t>{text}</w:t></w:r>" for text in runs) + "</w:p>"
        for runs in paragraphs
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><w:{root} xmlns:w="{W_NS}">{content}</w:{root}>'
    ).encode()


def _document(inner: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>{inner}<w:sectPr/>'
        "</w:body></w:document>"
    ).encode()


def _paragraph(*runs: str) -> str:
    return "<w:p>" + "".join(f"<w:r><w:t>{text}</w:t></w:r>" for text in runs) + "</w:p>"


def test_supported_text_part_allowlist_is_explicit() -> None:
    assert SUPPORTED_TEXT_PARTS == (
        "word/document.xml",
        "word/header*.xml",
        "word/footer*.xml",
        "word/footnotes.xml",
        "word/endnotes.xml",
    )


@pytest.mark.parametrize(
    ("part_name", "content"),
    [
        ("word/document.xml", word_document((("{{ document.title }}",),))),
        ("word/header1.xml", _part("hdr", (("{{ document.title }}",),))),
        ("word/footer2.xml", _part("ftr", (("{{ document.title }}",),))),
        ("word/footnotes.xml", _part("footnotes", (("{{ document.title }}",),))),
        ("word/endnotes.xml", _part("endnotes", (("{{ document.title }}",),))),
    ],
)
def test_discovers_required_variable_in_every_supported_part(
    part_name: str, content: bytes
) -> None:
    entries = {
        "word/document.xml": word_document((("Synthetic",),)),
        part_name: content,
    }
    if part_name == "word/document.xml":
        entries = {part_name: content}

    result = validate_template(minimal_docx(entries=entries), _registration())

    assert result.is_valid
    assert result.variables == ("document.title",)


def test_discovers_variables_in_table_cells_and_rows() -> None:
    table = "<w:tbl><w:tr><w:tc>" + _paragraph("{{ document.title }}") + "</w:tc></w:tr></w:tbl>"

    assert validate_template(
        minimal_docx(entries={"word/document.xml": _document(table)}), _registration()
    ).is_valid


def test_optional_variable_may_be_present_or_absent_but_required_may_not() -> None:
    optional = word_document((("{{ document.title }} {{ document.notes }}",),))
    required_only = word_document((("{{ document.title }}",),))
    missing = word_document((("{{ document.notes }}",),))

    assert validate_template(
        minimal_docx(entries={"word/document.xml": optional}), _registration()
    ).is_valid
    assert validate_template(
        minimal_docx(entries={"word/document.xml": required_only}), _registration()
    ).is_valid
    assert TemplateErrorCategory.MISSING_REQUIRED_VARIABLE in _categories(
        minimal_docx(entries={"word/document.xml": missing})
    )


def test_unknown_variable_is_rejected() -> None:
    package = minimal_docx(
        entries={"word/document.xml": word_document((("{{ document.secret }}",),))}
    )
    assert TemplateErrorCategory.UNKNOWN_VARIABLE in _categories(package)


@pytest.mark.parametrize(
    "source",
    [
        "{{ document.title ",
        "{{ document.title }",
        "{% if document.title %}{{ document.title }}",
        "{{ document.title + }}",
        "{% %}{{ document.title }}",
    ],
)
def test_malformed_delimiters_and_jinja_are_rejected(source: str) -> None:
    package = minimal_docx(entries={"word/document.xml": word_document(((source,),))})
    result = _categories(package)
    assert {
        TemplateErrorCategory.MALFORMED_DELIMITER,
        TemplateErrorCategory.MALFORMED_JINJA,
    }.intersection(result)


@pytest.mark.parametrize(
    "runs",
    [
        ("{", "{ document.title }}"),
        ("{{ document.title }", "}"),
        ("{{ document.", "title }}"),
    ],
)
def test_split_delimiters_or_variable_names_are_rejected(runs: tuple[str, str]) -> None:
    package = minimal_docx(entries={"word/document.xml": word_document((runs,))})
    assert TemplateErrorCategory.SPLIT_TOKEN in _categories(package)


def test_partially_styled_placeholder_is_rejected_but_whole_token_style_is_valid() -> None:
    partial = _document(
        "<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>{{ document.</w:t></w:r>"
        "<w:r><w:t>title }}</w:t></w:r></w:p>"
    )
    whole = _document("<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>{{ document.title }}</w:t></w:r></w:p>")

    assert TemplateErrorCategory.PARTIAL_STYLE in _categories(
        minimal_docx(entries={"word/document.xml": partial})
    )
    assert validate_template(
        minimal_docx(entries={"word/document.xml": whole}), _registration()
    ).is_valid


def test_valid_loop_and_condition_are_discovered() -> None:
    registration = _registration(
        required=(PlaceholderDefinition("document.items", PlaceholderValueKind.LIST),),
        optional=(PlaceholderDefinition("document.notes", PlaceholderValueKind.TEXT),),
    )
    source = (
        "{% for item in document.items %}{{ item }}{% endfor %}"
        "{% if document.notes %}{{ document.notes }}{% endif %}"
    )
    result = validate_template(
        minimal_docx(entries={"word/document.xml": word_document(((source,),))}),
        registration,
    )
    assert result.is_valid
    assert result.variables == ("document.items", "document.notes")


def test_filtered_loop_with_tuple_target_stays_inside_local_scope() -> None:
    registration = _registration(
        required=(PlaceholderDefinition("document.items", PlaceholderValueKind.LIST),),
        optional=(),
    )
    source = "{% for first, second in document.items if first %}{{ second }}{% endfor %}"
    assert validate_template(
        minimal_docx(entries={"word/document.xml": word_document(((source,),))}),
        registration,
    ).is_valid


def test_loop_source_must_have_the_declared_list_kind() -> None:
    source = "{% for item in document.title %}{{ item }}{% endfor %}"
    assert TemplateErrorCategory.VALUE_KIND_MISMATCH in _categories(
        minimal_docx(entries={"word/document.xml": word_document(((source,),))})
    )


@pytest.mark.parametrize(
    ("kind", "valid_xml", "invalid_xml"),
    [
        (
            "p",
            _document(_paragraph("{%p if document.title %}") + _paragraph("{%p endif %}")),
            _document(_paragraph("prefix {%p if document.title %}")),
        ),
        (
            "tr",
            _document(
                "<w:tbl><w:tr><w:tc>"
                + _paragraph("{%tr if document.title %}")
                + "</w:tc></w:tr><w:tr><w:tc>"
                + _paragraph("{%tr endif %}")
                + "</w:tc></w:tr></w:tbl>"
            ),
            _document(_paragraph("{%tr if document.title %}")),
        ),
        (
            "tc",
            _document(
                "<w:tbl><w:tr><w:tc>"
                + _paragraph("{%tc if document.title %}")
                + "</w:tc><w:tc>"
                + _paragraph("{%tc endif %}")
                + "</w:tc></w:tr></w:tbl>"
            ),
            _document(_paragraph("{%tc if document.title %}")),
        ),
        (
            "r",
            _document(_paragraph("{%r if document.title %}") + _paragraph("{%r endif %}")),
            _document("<w:p><w:r><w:t>prefix {%r if document.title %}</w:t></w:r></w:p>"),
        ),
    ],
)
def test_docxtpl_structural_tags_require_their_own_supported_container(
    kind: str, valid_xml: bytes, invalid_xml: bytes
) -> None:
    assert validate_template(
        minimal_docx(entries={"word/document.xml": valid_xml}), _registration()
    ).is_valid, kind
    assert TemplateErrorCategory.UNSUPPORTED_STRUCTURE in _categories(
        minimal_docx(entries={"word/document.xml": invalid_xml})
    )


def test_multiple_structural_tags_in_one_container_are_rejected() -> None:
    source = "{%p if document.title %}{%p endif %}"
    assert TemplateErrorCategory.UNSUPPORTED_STRUCTURE in _categories(
        minimal_docx(entries={"word/document.xml": word_document(((source,),))})
    )


def test_unsupported_text_part_with_template_syntax_is_not_silently_ignored() -> None:
    package = minimal_docx(
        entries={
            "word/document.xml": word_document((("{{ document.title }}",),)),
            "word/comments.xml": _part("comments", (("{{ document.notes }}",),)),
        }
    )
    assert TemplateErrorCategory.UNSUPPORTED_PART in _categories(package)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_template_syntax_in_unsupported_xml_encoding_is_not_ignored(encoding: str) -> None:
    comments = (
        f'<?xml version="1.0" encoding="{encoding}"?>'
        f'<w:comments xmlns:w="{W_NS}"><w:comment>{{{{ document.notes }}}}</w:comment>'
        "</w:comments>"
    ).encode(encoding)
    package = minimal_docx(
        entries={
            "word/document.xml": word_document((("{{ document.title }}",),)),
            "word/comments.xml": comments,
        }
    )
    assert TemplateErrorCategory.UNSUPPORTED_PART in _categories(package)


def test_template_syntax_in_non_visible_supported_xml_node_is_rejected() -> None:
    document = _document(
        "<w:p><w:r><w:t>{{ document.title }}</w:t>"
        "<w:instrText>{{ document.notes }}</w:instrText></w:r></w:p>"
    )
    assert TemplateErrorCategory.UNSUPPORTED_STRUCTURE in _categories(
        minimal_docx(entries={"word/document.xml": document})
    )


@pytest.mark.parametrize(
    "inner",
    [
        "<w:t>{{ document.title }}</w:t>",
        '<w:p data-template="{{ document.title }}"><w:r><w:t>Synthetic</w:t></w:r></w:p>',
    ],
)
def test_template_syntax_outside_supported_visible_run_text_is_rejected(inner: str) -> None:
    assert TemplateErrorCategory.UNSUPPORTED_STRUCTURE in _categories(
        minimal_docx(entries={"word/document.xml": _document(inner)})
    )


def test_allowed_and_disallowed_filters_follow_both_contract_and_platform_catalog() -> None:
    package = minimal_docx(
        entries={"word/document.xml": word_document((("{{ document.title|upper }}",),))}
    )
    assert validate_template(package, _registration(filters=frozenset({"upper"}))).is_valid
    assert TemplateErrorCategory.DISALLOWED_FILTER in _categories(package)
    assert TemplateErrorCategory.DISALLOWED_FILTER in _categories(
        package, registration=_registration(filters=frozenset({"unsafe_filter"}))
    )


def test_filter_use_must_match_the_registry_value_kind() -> None:
    registration = _registration(
        required=(PlaceholderDefinition("document.items", PlaceholderValueKind.LIST),),
        optional=(),
        filters=frozenset({"upper"}),
    )
    package = minimal_docx(
        entries={"word/document.xml": word_document((("{{ document.items|upper }}",),))}
    )
    result = validate_template(package, registration)
    assert TemplateErrorCategory.VALUE_KIND_MISMATCH in tuple(
        finding.category for finding in result.findings
    )


def test_allowed_and_disallowed_globals_follow_both_contract_and_platform_catalog() -> None:
    package = minimal_docx(
        entries={
            "word/document.xml": word_document(
                (("{% if platform_flag %}{{ document.title }}{% endif %}",),)
            )
        }
    )
    assert validate_template(package, _registration(globals_=frozenset({"platform_flag"}))).is_valid
    assert TemplateErrorCategory.DISALLOWED_GLOBAL in _categories(package)


@pytest.mark.parametrize(
    ("source", "category"),
    [
        ("{{ platform_flag() }} {{ document.title }}", TemplateErrorCategory.DISALLOWED_CALL),
        ("{% import 'x' as x %}{{ document.title }}", TemplateErrorCategory.DISALLOWED_EXPRESSION),
        ("{{ document.__class__ }}", TemplateErrorCategory.UNSAFE_ATTRIBUTE),
        ("{{ document['title'] }}", TemplateErrorCategory.DISALLOWED_EXPRESSION),
        ("{{ [1, 2] }} {{ document.title }}", TemplateErrorCategory.DISALLOWED_EXPRESSION),
        (
            "{% for item in document.items %}{{ item.name }}{% endfor %}",
            TemplateErrorCategory.UNSAFE_ATTRIBUTE,
        ),
    ],
)
def test_calls_imports_unsafe_attributes_and_dynamic_expressions_are_rejected(
    source: str, category: TemplateErrorCategory
) -> None:
    assert category in _categories(
        minimal_docx(entries={"word/document.xml": word_document(((source,),))})
    )


def test_invalid_package_stops_before_jinja_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Jinja parsing must not run")

    monkeypatch.setattr("jinja2.Environment.parse", forbidden)
    result = validate_template(b"not a package", _registration())
    assert tuple(f.category for f in result.findings) == (TemplateErrorCategory.PACKAGE_INVALID,)


def test_restricted_environment_escapes_values_and_never_reparses_jinja_looking_data() -> None:
    environment = create_restricted_environment(_registration().placeholder_contract)
    assert environment.undefined is StrictUndefined
    rendered = environment.from_string("{{ document.title }}").render(
        document={"title": "<tag>{{ platform_flag() }}</tag>"}
    )
    assert rendered == "&lt;tag&gt;{{ platform_flag() }}&lt;/tag&gt;"
    assert (
        environment.from_string("{{ document.title }}").render(
            document={"title": Markup("<b>synthetic</b>")}
        )
        == "&lt;b&gt;synthetic&lt;/b&gt;"
    )
    with pytest.raises(UndefinedError):
        environment.from_string("{{ document.title }}").render(document={})
    with pytest.raises(SecurityError):
        environment.from_string("{{ value.upper() }}").render(value="synthetic")


def test_findings_are_safe_bounded_deterministic_and_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive = "synthetic-private-marker"
    package = minimal_docx(
        entries={"word/document.xml": word_document(((f"{{{{ document.{sensitive} }}}}",),))}
    )
    with caplog.at_level(logging.DEBUG):
        first = validate_template(package, _registration())
        second = validate_template(package, _registration())

    assert first == second
    assert len(first.findings) <= 50
    assert all(len(finding.part) <= 80 for finding in first.findings)
    assert all(len(finding.location) <= 80 for finding in first.findings)
    assert sensitive not in repr(first)
    assert sensitive not in caplog.text


def test_package_bytes_are_not_modified_and_validation_is_reusable() -> None:
    package = minimal_docx(
        entries={"word/document.xml": word_document((("{{ document.title }}",),))}
    )
    original = bytes(package)

    assert validate_template(package, _registration()).is_valid
    assert validate_template(package, _registration()).is_valid
    assert package == original


def test_oversized_bytes_stop_before_copying_or_parsing() -> None:
    oversized = memoryview(b"P" * (10 * 1024 * 1024 + 1))
    assert validate_template(oversized, _registration()).findings == (
        validate_template(oversized, _registration())
        .findings[0]
        .__class__(TemplateErrorCategory.PACKAGE_INVALID, "template", "template"),
    )


@pytest.mark.parametrize("separator", ["<w:tab/>", "<w:br/>"])
def test_compatible_whitespace_elements_inside_one_run_are_reconstructed(
    separator: str,
) -> None:
    document = _document(
        f"<w:p><w:r><w:t>{{{{</w:t>{separator}<w:t>document.title }}}}</w:t></w:r></w:p>"
    )
    assert validate_template(
        minimal_docx(entries={"word/document.xml": document}), _registration()
    ).is_valid


def test_template_source_size_limit_accepts_exact_boundary_and_rejects_above() -> None:
    token = "{{ document.title }}"
    at_limit = token + "x" * (DEFAULT_TEMPLATE_LIMITS.max_source_characters - len(token))
    above_limit = at_limit + "x"

    assert validate_template(
        stored_docx(entries={"word/document.xml": word_document(((at_limit,),))}),
        _registration(),
    ).is_valid
    assert TemplateErrorCategory.COMPLEXITY_LIMIT in _categories(
        stored_docx(entries={"word/document.xml": word_document(((above_limit,),))})
    )


def test_control_nesting_limit_accepts_exact_boundary_and_rejects_above() -> None:
    def nested(depth: int) -> str:
        return "{% if document.title %}" * depth + "{{ document.title }}" + "{% endif %}" * depth

    limits = TemplateValidationLimits(max_control_nesting=3)
    assert validate_template(
        minimal_docx(entries={"word/document.xml": word_document(((nested(3),),))}),
        _registration(),
        limits=limits,
    ).is_valid
    result = validate_template(
        minimal_docx(entries={"word/document.xml": word_document(((nested(4),),))}),
        _registration(),
        limits=limits,
    )
    assert TemplateErrorCategory.COMPLEXITY_LIMIT in tuple(
        finding.category for finding in result.findings
    )


def test_template_limits_reject_fail_open_values() -> None:
    with pytest.raises(ValueError, match="positive"):
        TemplateValidationLimits(max_ast_nodes=0)


def test_token_and_ast_complexity_limits_fail_closed() -> None:
    package = minimal_docx(
        entries={"word/document.xml": word_document((("{{ ((document.title)) }}",),))}
    )
    bracket_result = validate_template(
        package,
        _registration(),
        limits=TemplateValidationLimits(max_control_nesting=1),
    )
    ast_result = validate_template(
        package,
        _registration(),
        limits=TemplateValidationLimits(max_ast_nodes=1),
    )
    assert TemplateErrorCategory.COMPLEXITY_LIMIT in tuple(
        finding.category for finding in bracket_result.findings
    )
    assert TemplateErrorCategory.COMPLEXITY_LIMIT in tuple(
        finding.category for finding in ast_result.findings
    )


def test_parser_recursion_is_converted_to_a_safe_complexity_finding() -> None:
    package = minimal_docx(
        entries={"word/document.xml": word_document((("{{ document.title }}",),))}
    )
    with patch.object(Environment, "parse", side_effect=RecursionError):
        result = validate_template(package, _registration())
    assert TemplateErrorCategory.COMPLEXITY_LIMIT in tuple(
        finding.category for finding in result.findings
    )
