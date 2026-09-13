from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol

from django import forms
from django.forms.formsets import BaseFormSet

from apps.documents.storage_keys import sanitize_template_display_filename


class InvalidDocumentRegistration(ValueError):
    """Raised when reviewed registry code has an incomplete or unsafe contract."""


class UnknownDocumentTypeKey(LookupError):
    """Raised when a key is not present in the deployed registry."""


class PlaceholderValueKind(StrEnum):
    TEXT = "text"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    DECIMAL = "decimal"
    INTEGER = "integer"
    LIST = "list"
    MAPPING = "mapping"


class RelatedObjectKind(StrEnum):
    CASE_PARTICIPANT = "case_participant"


@dataclass(frozen=True, slots=True)
class PlaceholderDefinition:
    name: str
    value_kind: PlaceholderValueKind


@dataclass(frozen=True, slots=True)
class PlaceholderContract:
    required: tuple[PlaceholderDefinition, ...]
    optional: tuple[PlaceholderDefinition, ...] = ()
    allowed_filters: frozenset[str] = frozenset()
    allowed_globals: frozenset[str] = frozenset()

    @property
    def required_names(self) -> frozenset[str]:
        return frozenset(item.name for item in self.required)

    @property
    def optional_names(self) -> frozenset[str]:
        return frozenset(item.name for item in self.optional)

    @property
    def expected_kinds(self) -> Mapping[str, PlaceholderValueKind]:
        return MappingProxyType(
            {item.name: item.value_kind for item in (*self.required, *self.optional)}
        )


@dataclass(frozen=True, slots=True)
class DocumentFormBundle:
    form_class: type[forms.Form]
    formset_classes: tuple[type[BaseFormSet[forms.Form]], ...] = ()


class FormProvider(Protocol):
    def __call__(self) -> DocumentFormBundle: ...


class ContextMapper(Protocol):
    def __call__(self, values: Mapping[str, Any]) -> Mapping[str, Any]: ...


class FilenameBuilder(Protocol):
    def __call__(self, values: Mapping[str, Any]) -> str: ...


class FixtureProvider(Protocol):
    def __call__(self) -> Mapping[str, Any]: ...


class PostProcessor(Protocol):
    def __call__(self, document_path: str) -> None: ...


@dataclass(frozen=True, slots=True)
class DocumentRegistration:
    key: str
    official_code: str
    vietnamese_name: str
    english_name: str | None
    enabled: bool
    schema_version: str
    form_provider: FormProvider
    context_mapper: ContextMapper
    filename_builder: FilenameBuilder
    placeholder_contract: PlaceholderContract
    minimal_fixture: FixtureProvider
    representative_fixture: FixtureProvider
    is_synthetic: bool = False
    post_processor_name: str | None = None
    related_fields: tuple[RelatedFieldDefinition, ...] = ()


@dataclass(frozen=True, slots=True)
class RelatedFieldDefinition:
    name: str
    object_kind: RelatedObjectKind
    formset_prefix: str | None = None


_PRODUCTION_KEY = re.compile(r"^vds-[0-9]{2}$")
_SYNTHETIC_KEY = re.compile(r"^synthetic-[a-z0-9]+(?:-[a-z0-9]+)*$")
_PLACEHOLDER_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_ALLOWLIST_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
RESERVED_DRAFT_FIELD_NAMES = frozenset(
    {
        "case",
        "court",
        "participants",
        "rendered_context",
        "snapshot",
        "template_source",
    }
)


def _matches_value_kind(value: object, kind: PlaceholderValueKind) -> bool:
    if kind is PlaceholderValueKind.TEXT:
        return isinstance(value, str)
    if kind is PlaceholderValueKind.BOOLEAN:
        return isinstance(value, bool)
    if kind is PlaceholderValueKind.DATETIME:
        return isinstance(value, datetime)
    if kind is PlaceholderValueKind.DATE:
        return isinstance(value, date) and not isinstance(value, datetime)
    if kind is PlaceholderValueKind.DECIMAL:
        return isinstance(value, Decimal)
    if kind is PlaceholderValueKind.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if kind is PlaceholderValueKind.LIST:
        return isinstance(value, (list, tuple))
    return isinstance(value, Mapping)


class DocumentRegistry:
    """Immutable, code-owned descriptions of supported document types.

    A successful lookup only proves that code knows the type. Availability and
    authorization remain separate selector and service responsibilities.
    """

    def __init__(
        self,
        registrations: tuple[DocumentRegistration, ...],
        *,
        post_processors: Mapping[str, PostProcessor] | None = None,
    ) -> None:
        declared_post_processors = MappingProxyType(dict(post_processors or {}))
        if any(
            not _ALLOWLIST_NAME.fullmatch(name) or not callable(processor)
            for name, processor in declared_post_processors.items()
        ):
            raise InvalidDocumentRegistration(
                "Each post-processor must be explicitly named and callable."
            )
        by_key: dict[str, DocumentRegistration] = {}
        official_codes: set[str] = set()
        for registration in registrations:
            self._validate_registration(registration, declared_post_processors)
            if registration.key in by_key:
                raise InvalidDocumentRegistration(
                    f"Duplicate document type key: {registration.key}"
                )
            if registration.official_code in official_codes:
                raise InvalidDocumentRegistration(
                    f"Duplicate official code: {registration.official_code}"
                )
            by_key[registration.key] = registration
            official_codes.add(registration.official_code)
        self._registrations = MappingProxyType(by_key)
        self._post_processors = declared_post_processors

    @staticmethod
    def _validate_registration(
        registration: DocumentRegistration,
        post_processors: Mapping[str, PostProcessor],
    ) -> None:
        if not isinstance(registration, DocumentRegistration):
            raise InvalidDocumentRegistration("Each registry entry must be a typed registration.")
        if not isinstance(registration.enabled, bool) or not isinstance(
            registration.is_synthetic, bool
        ):
            raise InvalidDocumentRegistration("Registry state flags must be boolean values.")
        if not isinstance(registration.english_name, (str, type(None))):
            raise InvalidDocumentRegistration("The optional English name must be text.")
        valid_key = (registration.is_synthetic and _SYNTHETIC_KEY.fullmatch(registration.key)) or (
            not registration.is_synthetic and _PRODUCTION_KEY.fullmatch(registration.key)
        )
        if not valid_key:
            raise InvalidDocumentRegistration("Invalid stable key format.")
        if not registration.official_code.strip():
            raise InvalidDocumentRegistration("A non-empty official code is required.")
        if not registration.vietnamese_name.strip():
            raise InvalidDocumentRegistration("A non-empty Vietnamese name is required.")
        if not re.fullmatch(r"v[1-9][0-9]*", registration.schema_version):
            raise InvalidDocumentRegistration("A stable schema version is required.")

        providers = (
            ("form provider", registration.form_provider),
            ("context mapper", registration.context_mapper),
            ("filename builder", registration.filename_builder),
            ("minimal fixture provider", registration.minimal_fixture),
            ("representative fixture provider", registration.representative_fixture),
        )
        for name, provider in providers:
            if not callable(provider):
                raise InvalidDocumentRegistration(f"A callable {name} is required.")

        form_bundle = registration.form_provider()
        if (
            not isinstance(form_bundle, DocumentFormBundle)
            or not isinstance(form_bundle.formset_classes, tuple)
            or not isinstance(form_bundle.form_class, type)
            or not issubclass(form_bundle.form_class, forms.Form)
        ):
            raise InvalidDocumentRegistration("The form provider must return a Django Form bundle.")
        if any(
            not isinstance(formset, type) or not issubclass(formset, BaseFormSet)
            for formset in form_bundle.formset_classes
        ):
            raise InvalidDocumentRegistration("The form provider returned an invalid formset.")
        formset_prefixes = tuple(
            formset.get_default_prefix() for formset in form_bundle.formset_classes
        )
        if len(formset_prefixes) != len(set(formset_prefixes)):
            raise InvalidDocumentRegistration("Each formset must have a unique stable prefix.")
        formsets_by_prefix = dict(zip(formset_prefixes, form_bundle.formset_classes, strict=True))
        stored_names = (
            *form_bundle.form_class.base_fields,
            *formset_prefixes,
            *(name for formset in form_bundle.formset_classes for name in formset.form.base_fields),
        )
        if any(
            _ALLOWLIST_NAME.fullmatch(name) is None or name in RESERVED_DRAFT_FIELD_NAMES
            for name in stored_names
        ):
            raise InvalidDocumentRegistration(
                "Form and formset fields must use stable safe identifiers."
            )
        related_paths = [
            (field.formset_prefix, field.name) for field in registration.related_fields
        ]
        if len(related_paths) != len(set(related_paths)) or any(
            not isinstance(field, RelatedFieldDefinition)
            or not isinstance(field.object_kind, RelatedObjectKind)
            or (
                field.formset_prefix is None
                and (
                    field.name not in form_bundle.form_class.base_fields
                    or not isinstance(
                        form_bundle.form_class.base_fields[field.name], forms.UUIDField
                    )
                )
            )
            or (
                field.formset_prefix is not None
                and (
                    field.formset_prefix not in formsets_by_prefix
                    or field.name not in formsets_by_prefix[field.formset_prefix].form.base_fields
                    or not isinstance(
                        formsets_by_prefix[field.formset_prefix].form.base_fields[field.name],
                        forms.UUIDField,
                    )
                )
            )
            for field in registration.related_fields
        ):
            raise InvalidDocumentRegistration(
                "Related fields must be unique UUID fields declared by the form or formsets."
            )

        fixtures: list[Mapping[str, Any]] = []
        for provider in (registration.minimal_fixture, registration.representative_fixture):
            fixture = provider()
            if not isinstance(fixture, Mapping):
                raise InvalidDocumentRegistration("Each fixture provider must return a mapping.")
            fixtures.append(fixture)

        contract = registration.placeholder_contract
        if (
            not isinstance(contract, PlaceholderContract)
            or not isinstance(contract.required, tuple)
            or not isinstance(contract.optional, tuple)
            or not isinstance(contract.allowed_filters, frozenset)
            or not isinstance(contract.allowed_globals, frozenset)
        ):
            raise InvalidDocumentRegistration(
                "The placeholder contract must be typed and immutable."
            )
        definitions = (*contract.required, *contract.optional)
        if any(
            not isinstance(definition, PlaceholderDefinition)
            or not isinstance(definition.name, str)
            or not isinstance(definition.value_kind, PlaceholderValueKind)
            for definition in definitions
        ):
            raise InvalidDocumentRegistration("The placeholder contract has an invalid value kind.")
        names = [definition.name for definition in definitions]
        if not contract.required or len(names) != len(set(names)):
            raise InvalidDocumentRegistration(
                "The placeholder contract is incomplete or duplicated."
            )
        if any(not _PLACEHOLDER_NAME.fullmatch(name) for name in names):
            raise InvalidDocumentRegistration("The placeholder contract contains an invalid name.")
        allowlist_names = (*contract.allowed_filters, *contract.allowed_globals)
        if any(not _ALLOWLIST_NAME.fullmatch(name) for name in allowlist_names):
            raise InvalidDocumentRegistration("The placeholder allowlist contains an invalid name.")
        if (
            registration.post_processor_name is not None
            and registration.post_processor_name not in post_processors
        ):
            raise InvalidDocumentRegistration("The named post-processor is not declared.")

        declared_names = set(names)
        for fixture in fixtures:
            form = form_bundle.form_class(data=fixture)
            if not form.is_valid():
                raise InvalidDocumentRegistration("Each fixture must satisfy the registry form.")
            cleaned_values: dict[str, Any] = dict(form.cleaned_data)
            for prefix, formset_class in zip(
                formset_prefixes, form_bundle.formset_classes, strict=True
            ):
                formset = formset_class(data=fixture, prefix=prefix)
                if not formset.is_valid():
                    raise InvalidDocumentRegistration(
                        "Each fixture must satisfy every registry formset."
                    )
                cleaned_values[prefix] = tuple(
                    MappingProxyType(dict(row)) for row in formset.cleaned_data
                )
            context = registration.context_mapper(MappingProxyType(cleaned_values))
            if not isinstance(context, Mapping):
                raise InvalidDocumentRegistration("The context mapper must return a mapping.")
            if not contract.required_names.issubset(context) or not set(context).issubset(
                declared_names
            ):
                raise InvalidDocumentRegistration(
                    "The context mapper and placeholder contract are incomplete."
                )
            for name, value in context.items():
                if not _matches_value_kind(value, contract.expected_kinds[name]):
                    raise InvalidDocumentRegistration(
                        "The context mapper returned a value with the wrong declared value kind."
                    )
            filename = registration.filename_builder(MappingProxyType(cleaned_values))
            if (
                not isinstance(filename, str)
                or not filename.lower().endswith(".docx")
                or sanitize_template_display_filename(filename) != filename
            ):
                raise InvalidDocumentRegistration("The filename builder returned an unsafe name.")

    def get(self, key: str) -> DocumentRegistration:
        try:
            return self._registrations[key]
        except KeyError as error:
            raise UnknownDocumentTypeKey(key) from error

    def describe(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "key": registration.key,
                "official_code": registration.official_code,
                "vietnamese_name": registration.vietnamese_name,
                "english_name": registration.english_name,
                "enabled": registration.enabled,
                "schema_version": registration.schema_version,
                "is_synthetic": registration.is_synthetic,
                "required_placeholders": tuple(
                    sorted(registration.placeholder_contract.required_names)
                ),
                "optional_placeholders": tuple(
                    sorted(registration.placeholder_contract.optional_names)
                ),
                "allowed_filters": tuple(sorted(registration.placeholder_contract.allowed_filters)),
                "allowed_globals": tuple(sorted(registration.placeholder_contract.allowed_globals)),
                "post_processor_name": registration.post_processor_name,
            }
            for registration in self._registrations.values()
        )


class SyntheticDocumentForm(forms.Form):
    title = forms.CharField(max_length=200)
    notes = forms.CharField(required=False, max_length=1000)
    participant_id = forms.UUIDField(required=False)


def _synthetic_form_provider() -> DocumentFormBundle:
    return DocumentFormBundle(form_class=SyntheticDocumentForm)


def _synthetic_context_mapper(values: Mapping[str, Any]) -> Mapping[str, Any]:
    context: dict[str, Any] = {"document.title": values["title"]}
    if notes := values.get("notes"):
        context["document.notes"] = notes
    return MappingProxyType(context)


def _synthetic_filename_builder(values: Mapping[str, Any]) -> str:
    return "synthetic-document.docx"


def _synthetic_minimal_fixture() -> Mapping[str, Any]:
    return MappingProxyType({"title": "Tài liệu kiểm thử tổng hợp"})


def _synthetic_representative_fixture() -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "title": "Tài liệu đại diện kiểm thử tổng hợp",
            "notes": "Nội dung tổng hợp có dấu tiếng Việt",
        }
    )


document_registry = DocumentRegistry(
    (
        DocumentRegistration(
            key="synthetic-platform-test",
            official_code="SYNTHETIC-DOC",
            vietnamese_name="Biểu mẫu kiểm thử nền tảng",
            english_name="Synthetic platform test document",
            enabled=True,
            schema_version="v1",
            form_provider=_synthetic_form_provider,
            context_mapper=_synthetic_context_mapper,
            filename_builder=_synthetic_filename_builder,
            placeholder_contract=PlaceholderContract(
                required=(PlaceholderDefinition("document.title", PlaceholderValueKind.TEXT),),
                optional=(PlaceholderDefinition("document.notes", PlaceholderValueKind.TEXT),),
                allowed_filters=frozenset({"default"}),
            ),
            minimal_fixture=_synthetic_minimal_fixture,
            representative_fixture=_synthetic_representative_fixture,
            is_synthetic=True,
            related_fields=(
                RelatedFieldDefinition("participant_id", RelatedObjectKind.CASE_PARTICIPANT),
            ),
        ),
    )
)
