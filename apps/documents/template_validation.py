from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Final
from zipfile import ZipFile

from jinja2 import Environment, StrictUndefined, Undefined, nodes
from jinja2.exceptions import TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment
from jinja2.visitor import NodeVisitor

from apps.documents.limits import (
    DEFAULT_TEMPLATE_LIMITS,
    MAX_TEMPLATE_BYTES,
    TemplateValidationLimits,
)
from apps.documents.package_validation import validate_docx_package
from apps.documents.registry import (
    DocumentRegistration,
    PlaceholderContract,
    PlaceholderValueKind,
)

SUPPORTED_TEXT_PARTS: Final = (
    "word/document.xml",
    "word/header*.xml",
    "word/footer*.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
)
MAX_TEMPLATE_FINDINGS: Final = 50
MAX_PART_LABEL_LENGTH: Final = 80
MAX_LOCATION_LENGTH: Final = 80

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{_WORD_NAMESPACE}}}"
_TOKEN = re.compile(r"(?:{{.*?}}|{%.*?%}|{#.*?#})", re.DOTALL)
_DELIMITER = re.compile(r"{{|}}|{%|%}|{#|#}")
_STRUCTURAL = re.compile(r"{%-?\s*(p|tr|tc|r)\s+(.+?)\s*-?%}", re.DOTALL)
_STRUCTURAL_PREFIX = re.compile(r"({%-?\s*)(?:p|tr|tc|r)\s+")
_HEADER = re.compile(r"word/header[0-9]+\.xml")
_FOOTER = re.compile(r"word/footer[0-9]+\.xml")
_SAFE_FILTER_NAMES = frozenset({"default", "length", "lower", "upper"})
_SAFE_FILTER_KINDS: Final = {
    "default": frozenset(PlaceholderValueKind),
    "length": frozenset(
        {
            PlaceholderValueKind.TEXT,
            PlaceholderValueKind.LIST,
            PlaceholderValueKind.MAPPING,
        }
    ),
    "lower": frozenset({PlaceholderValueKind.TEXT}),
    "upper": frozenset({PlaceholderValueKind.TEXT}),
}
_SAFE_GLOBAL_VALUES: Final = {"platform_flag": True}


class TemplateErrorCategory(StrEnum):
    PACKAGE_INVALID = "package_invalid"
    UNSUPPORTED_PART = "unsupported_part"
    MALFORMED_DELIMITER = "malformed_delimiter"
    MALFORMED_JINJA = "malformed_jinja"
    UNKNOWN_VARIABLE = "unknown_variable"
    MISSING_REQUIRED_VARIABLE = "missing_required_variable"
    DISALLOWED_FILTER = "disallowed_filter"
    DISALLOWED_GLOBAL = "disallowed_global"
    DISALLOWED_CALL = "disallowed_call"
    UNSAFE_ATTRIBUTE = "unsafe_attribute"
    DISALLOWED_EXPRESSION = "disallowed_expression"
    UNSUPPORTED_STRUCTURE = "unsupported_structure"
    SPLIT_TOKEN = "split_token"
    PARTIAL_STYLE = "partial_style"
    VALUE_KIND_MISMATCH = "value_kind_mismatch"
    COMPLEXITY_LIMIT = "complexity_limit"


@dataclass(frozen=True, slots=True, order=True)
class TemplateFinding:
    category: TemplateErrorCategory
    part: str
    location: str


@dataclass(frozen=True, slots=True)
class TemplateValidationResult:
    findings: tuple[TemplateFinding, ...]
    variables: tuple[str, ...]
    filters: tuple[str, ...]
    globals: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.findings


def _finding(
    category: TemplateErrorCategory,
    part: str = "template",
    location: str = "template",
) -> TemplateFinding:
    return TemplateFinding(
        category,
        part[:MAX_PART_LABEL_LENGTH],
        location[:MAX_LOCATION_LENGTH],
    )


def _part_kind(name: str) -> str | None:
    if name == "word/document.xml":
        return "document"
    if _HEADER.fullmatch(name):
        return "header"
    if _FOOTER.fullmatch(name):
        return "footer"
    if name == "word/footnotes.xml":
        return "footnotes"
    if name == "word/endnotes.xml":
        return "endnotes"
    return None


def _run_text(run: ET.Element) -> str:
    pieces: list[str] = []
    for element in run.iter():
        if element.tag == f"{_W}t":
            pieces.append(element.text or "")
        elif element.tag == f"{_W}tab":
            pieces.append("\t")
        elif element.tag in {f"{_W}br", f"{_W}cr"}:
            pieces.append("\n")
    return "".join(pieces)


def _element_text(element: ET.Element) -> str:
    return "".join(_run_text(run) for run in element.iter(f"{_W}r"))


def _run_style(run: ET.Element) -> str:
    properties = run.find(f"{_W}rPr")
    return ET.tostring(properties, encoding="unicode") if properties is not None else ""


def _contains_template_syntax(root: ET.Element) -> bool:
    return any(
        _DELIMITER.search(value) is not None
        for element in root.iter()
        for value in (
            element.text or "",
            element.tail or "",
            *element.attrib.values(),
        )
    )


def _nearest(
    element: ET.Element,
    tag: str,
    parents: dict[ET.Element, ET.Element],
) -> ET.Element | None:
    current: ET.Element | None = element
    while current is not None:
        if current.tag == f"{_W}{tag}":
            return current
        current = parents.get(current)
    return None


def _has_unsupported_template_syntax(
    root: ET.Element, parents: dict[ET.Element, ET.Element]
) -> bool:
    for element in root.iter():
        if any(
            _DELIMITER.search(value) is not None
            for value in (element.tail or "", *element.attrib.values())
        ):
            return True
        if _DELIMITER.search(element.text or "") is None:
            continue
        if element.tag != f"{_W}t":
            return True
        if _nearest(element, "r", parents) is None or _nearest(element, "p", parents) is None:
            return True
    return False


def _normalized_source(source: str) -> str:
    return _STRUCTURAL_PREFIX.sub(r"\1", source)


def _bracket_depth_exceeds(source: str, maximum: int) -> bool:
    depth = 0
    for character in source:
        if character in "([":
            depth += 1
            if depth > maximum:
                return True
        elif character in ")]":
            depth = max(depth - 1, 0)
    return False


def _source_exceeds_limits(source: str, limits: TemplateValidationLimits) -> bool:
    if len(source) > limits.max_source_characters:
        return True
    tokens = tuple(_TOKEN.finditer(source))
    if len(tokens) > limits.max_tokens or any(
        len(token.group()) > limits.max_token_characters
        or _bracket_depth_exceeds(token.group(), limits.max_control_nesting)
        for token in tokens
    ):
        return True
    depth = 0
    for token in tokens:
        value = token.group()
        if not value.startswith("{%"):
            continue
        words = _STRUCTURAL_PREFIX.sub(r"\1", value)[2:-2].strip("- ").split(maxsplit=1)
        keyword = words[0] if words else ""
        if keyword in {"if", "for", "macro", "block", "call", "filter", "with", "autoescape"}:
            depth += 1
            if depth > limits.max_control_nesting:
                return True
        elif keyword.startswith("end"):
            depth = max(depth - 1, 0)
    return False


def _ast_exceeds_limits(root: nodes.Node, limits: TemplateValidationLimits) -> bool:
    count = 0
    pending = [(root, 1)]
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > limits.max_ast_nodes or depth > limits.max_ast_depth:
            return True
        pending.extend((child, depth + 1) for child in node.iter_child_nodes())
    return False


@dataclass(slots=True)
class _PartInspection:
    source: str
    findings: list[TemplateFinding]


def _inspect_part(root: ET.Element, part: str) -> _PartInspection:
    findings: list[TemplateFinding] = []
    sources: list[str] = []
    parents = {child: parent for parent in root.iter() for child in parent}
    paragraphs = tuple(root.iter(f"{_W}p"))
    if _has_unsupported_template_syntax(root, parents):
        findings.append(_finding(TemplateErrorCategory.UNSUPPORTED_STRUCTURE, part, "xml_text"))
    for paragraph_index, paragraph in enumerate(paragraphs):
        runs = tuple(paragraph.iter(f"{_W}r"))
        run_texts = tuple(_run_text(run) for run in runs)
        text = "".join(run_texts)
        if not _DELIMITER.search(text):
            continue
        sources.append(text)
        run_indexes: list[int] = []
        for run_index, value in enumerate(run_texts):
            run_indexes.extend([run_index] * len(value))
        spans = tuple(_TOKEN.finditer(text))
        masked = list(text)
        for match in spans:
            for offset in range(match.start(), match.end()):
                masked[offset] = " "
            touched = set(run_indexes[match.start() : match.end()])
            if len(touched) > 1:
                location = f"paragraph:{paragraph_index}"
                findings.append(_finding(TemplateErrorCategory.SPLIT_TOKEN, part, location))
                styles = {_run_style(runs[index]) for index in touched}
                if len(styles) > 1:
                    findings.append(_finding(TemplateErrorCategory.PARTIAL_STYLE, part, location))
            structural = _STRUCTURAL.fullmatch(match.group())
            if structural is None:
                continue
            kind = structural.group(1)
            first_run = runs[run_indexes[match.start()]]
            owner = _nearest(first_run, kind, parents)
            if owner is None or _element_text(owner).strip() != match.group().strip():
                findings.append(
                    _finding(
                        TemplateErrorCategory.UNSUPPORTED_STRUCTURE,
                        part,
                        f"paragraph:{paragraph_index}",
                    )
                )
                continue
        if _DELIMITER.search("".join(masked)):
            findings.append(
                _finding(
                    TemplateErrorCategory.MALFORMED_DELIMITER,
                    part,
                    f"paragraph:{paragraph_index}",
                )
            )
    return _PartInspection(_normalized_source("\n".join(sources)), findings)


def _attribute_path(node: nodes.Node) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, nodes.Getattr):
        parts.append(current.attr)
        current = current.node
    if not isinstance(current, nodes.Name):
        return None
    parts.append(current.name)
    return ".".join(reversed(parts))


class _ContractVisitor(NodeVisitor):
    def __init__(self, contract: PlaceholderContract, part: str) -> None:
        self.contract = contract
        self.part = part
        self.findings: list[TemplateFinding] = []
        self.variables: set[str] = set()
        self.filters: set[str] = set()
        self.globals: set[str] = set()
        self._locals: set[str] = set()

    def _add(self, category: TemplateErrorCategory) -> None:
        self.findings.append(_finding(category, self.part, "syntax"))

    def visit_Getattr(self, node: nodes.Getattr, *args: object, **kwargs: object) -> None:
        path = _attribute_path(node)
        if path is None or any(part.startswith("_") for part in path.split(".")):
            self._add(TemplateErrorCategory.UNSAFE_ATTRIBUTE)
        elif path in self.contract.expected_kinds:
            self.variables.add(path)
        elif path.split(".", 1)[0] in self._locals:
            self._add(TemplateErrorCategory.UNSAFE_ATTRIBUTE)
        else:
            self._add(TemplateErrorCategory.UNKNOWN_VARIABLE)

    def visit_Name(self, node: nodes.Name, *args: object, **kwargs: object) -> None:
        if node.ctx != "load" or node.name in self._locals:
            return
        if node.name in self.contract.allowed_globals and node.name in _SAFE_GLOBAL_VALUES:
            self.globals.add(node.name)
        else:
            self._add(TemplateErrorCategory.DISALLOWED_GLOBAL)

    def visit_Filter(self, node: nodes.Filter, *args: object, **kwargs: object) -> None:
        if node.name in self.contract.allowed_filters and node.name in _SAFE_FILTER_NAMES:
            self.filters.add(node.name)
            path = _attribute_path(node.node) if node.node is not None else None
            if (
                path is not None
                and path in self.contract.expected_kinds
                and self.contract.expected_kinds[path] not in _SAFE_FILTER_KINDS[node.name]
            ):
                self._add(TemplateErrorCategory.VALUE_KIND_MISMATCH)
        else:
            self._add(TemplateErrorCategory.DISALLOWED_FILTER)
        self.generic_visit(node, *args, **kwargs)

    def visit_Call(self, node: nodes.Call, *args: object, **kwargs: object) -> None:
        self._add(TemplateErrorCategory.DISALLOWED_CALL)
        self.generic_visit(node, *args, **kwargs)

    def visit_For(self, node: nodes.For, *args: object, **kwargs: object) -> None:
        path = _attribute_path(node.iter)
        if path is not None and path in self.contract.expected_kinds:
            self.variables.add(path)
            if self.contract.expected_kinds[path] is not PlaceholderValueKind.LIST:
                self._add(TemplateErrorCategory.VALUE_KIND_MISMATCH)
        else:
            self.visit(node.iter)
        target_names = {
            name.name for name in node.target.find_all(nodes.Name) if name.ctx == "store"
        }
        if isinstance(node.target, nodes.Name):
            target_names.add(node.target.name)
        previous = set(self._locals)
        self._locals.update(target_names)
        for child in (*node.body, *node.else_):
            self.visit(child)
        if node.test is not None:
            self.visit(node.test)
        self._locals = previous

    def _reject_expression(self, node: nodes.Node, *args: object, **kwargs: object) -> None:
        self._add(TemplateErrorCategory.DISALLOWED_EXPRESSION)
        self.generic_visit(node, *args, **kwargs)

    visit_Import = _reject_expression
    visit_FromImport = _reject_expression
    visit_Include = _reject_expression
    visit_Extends = _reject_expression
    visit_Macro = _reject_expression
    visit_CallBlock = _reject_expression
    visit_Assign = _reject_expression
    visit_AssignBlock = _reject_expression
    visit_Getitem = _reject_expression
    visit_Test = _reject_expression
    visit_Add = _reject_expression
    visit_Sub = _reject_expression
    visit_Mul = _reject_expression
    visit_Div = _reject_expression
    visit_FloorDiv = _reject_expression
    visit_Mod = _reject_expression
    visit_Pow = _reject_expression
    visit_Concat = _reject_expression
    visit_CondExpr = _reject_expression
    visit_List = _reject_expression
    visit_Dict = _reject_expression
    visit_Tuple = _reject_expression


class _RestrictedEnvironment(SandboxedEnvironment):
    def is_safe_attribute(self, obj: object, attr: str, value: object) -> bool:
        return False

    def is_safe_callable(self, obj: object) -> bool:
        return False


def _finalize_untrusted_value(value: object) -> object:
    return value if isinstance(value, Undefined) else str(value)


def create_restricted_environment(contract: PlaceholderContract) -> SandboxedEnvironment:
    """Return the fixed sandbox used only with package source that already passed validation."""
    baseline = Environment()
    environment = _RestrictedEnvironment(
        autoescape=True,
        undefined=StrictUndefined,
        finalize=_finalize_untrusted_value,
    )
    environment.filters.clear()
    environment.filters.update(
        {
            name: baseline.filters[name]
            for name in sorted(contract.allowed_filters & _SAFE_FILTER_NAMES)
        }
    )
    environment.globals.clear()
    environment.globals.update(
        {
            name: _SAFE_GLOBAL_VALUES[name]
            for name in sorted(contract.allowed_globals & _SAFE_GLOBAL_VALUES.keys())
        }
    )
    environment.tests.clear()
    return environment


def _result(
    findings: list[TemplateFinding],
    *,
    variables: set[str] | None = None,
    filters: set[str] | None = None,
    globals_: set[str] | None = None,
) -> TemplateValidationResult:
    return TemplateValidationResult(
        findings=tuple(sorted(set(findings)))[:MAX_TEMPLATE_FINDINGS],
        variables=tuple(sorted(variables or ())),
        filters=tuple(sorted(filters or ())),
        globals=tuple(sorted(globals_ or ())),
    )


def validate_template(
    package: bytes | bytearray | memoryview,
    registration: DocumentRegistration,
    *,
    limits: TemplateValidationLimits = DEFAULT_TEMPLATE_LIMITS,
) -> TemplateValidationResult:
    """Validate supported DOCX text parts against one immutable registry contract."""
    if len(package) > MAX_TEMPLATE_BYTES:
        return _result([_finding(TemplateErrorCategory.PACKAGE_INVALID)])
    package_bytes = bytes(package)
    if not validate_docx_package(package_bytes).is_valid:
        return _result([_finding(TemplateErrorCategory.PACKAGE_INVALID)])

    contract = registration.placeholder_contract
    findings: list[TemplateFinding] = []
    variables: set[str] = set()
    filters: set[str] = set()
    globals_: set[str] = set()
    sources: list[tuple[str, str]] = []
    with ZipFile(io.BytesIO(package_bytes)) as archive:
        text_part_number = 0
        for name in sorted(archive.namelist()):
            kind = _part_kind(name)
            content = archive.read(name)
            if kind is None:
                if (
                    name.startswith("word/")
                    and PurePosixPath(name).suffix.casefold() == ".xml"
                    and _contains_template_syntax(ET.fromstring(content))
                ):
                    findings.append(
                        _finding(
                            TemplateErrorCategory.UNSUPPORTED_PART,
                            "unsupported_part",
                            f"part:{text_part_number}",
                        )
                    )
                    text_part_number += 1
                continue
            root = ET.fromstring(content)
            inspection = _inspect_part(root, kind)
            findings.extend(inspection.findings)
            sources.append((kind, inspection.source))

    environment = create_restricted_environment(contract)
    for part, source in sources:
        if _source_exceeds_limits(source, limits):
            findings.append(_finding(TemplateErrorCategory.COMPLEXITY_LIMIT, part, "syntax"))
            continue
        try:
            parsed = environment.parse(source)
        except RecursionError:
            findings.append(_finding(TemplateErrorCategory.COMPLEXITY_LIMIT, part, "syntax"))
            continue
        except TemplateSyntaxError:
            findings.append(_finding(TemplateErrorCategory.MALFORMED_JINJA, part, "syntax"))
            continue
        if _ast_exceeds_limits(parsed, limits):
            findings.append(_finding(TemplateErrorCategory.COMPLEXITY_LIMIT, part, "syntax"))
            continue
        visitor = _ContractVisitor(contract, part)
        visitor.visit(parsed)
        findings.extend(visitor.findings)
        variables.update(visitor.variables)
        filters.update(visitor.filters)
        globals_.update(visitor.globals)

    for _missing in sorted(contract.required_names.difference(variables)):
        findings.append(_finding(TemplateErrorCategory.MISSING_REQUIRED_VARIABLE))
    return _result(
        findings,
        variables=variables,
        filters=filters,
        globals_=globals_,
    )
