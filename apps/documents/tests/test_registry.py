from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from django import forms
from django.forms import formset_factory

from apps.documents.registry import (
    DocumentFormBundle,
    DocumentRegistration,
    DocumentRegistry,
    InvalidDocumentRegistration,
    PlaceholderContract,
    PlaceholderDefinition,
    PlaceholderValueKind,
    UnknownDocumentTypeKey,
    document_registry,
)


def test_synthetic_registration_is_complete_immutable_and_not_production() -> None:
    registration = document_registry.get("synthetic-platform-test")

    assert registration.official_code == "SYNTHETIC-DOC"
    assert registration.is_synthetic is True
    assert registration.enabled is True
    assert registration.schema_version == "v1"
    assert registration.post_processor_name is None
    assert registration.form_provider().form_class.__name__ == "SyntheticDocumentForm"
    assert registration.form_provider().formset_classes == ()
    assert registration.context_mapper(registration.minimal_fixture()) == {
        "document.title": "Synthetic document"
    }
    assert registration.filename_builder(registration.minimal_fixture()).endswith(".docx")
    assert registration.representative_fixture()["notes"] == "Synthetic representative notes"
    assert registration.placeholder_contract.required_names == frozenset({"document.title"})
    assert registration.placeholder_contract.optional_names == frozenset({"document.notes"})
    assert registration.placeholder_contract.expected_kinds == {
        "document.title": PlaceholderValueKind.TEXT,
        "document.notes": PlaceholderValueKind.TEXT,
    }

    with pytest.raises(FrozenInstanceError):
        registration.enabled = False  # type: ignore[misc]


def test_registry_rejects_duplicate_keys_and_official_codes() -> None:
    registration = document_registry.get("synthetic-platform-test")

    with pytest.raises(InvalidDocumentRegistration, match="Duplicate document type key"):
        DocumentRegistry((registration, registration))

    duplicate_code = replace(registration, key="synthetic-other-test")
    with pytest.raises(InvalidDocumentRegistration, match="Duplicate official code"):
        DocumentRegistry((registration, duplicate_code))


def test_registry_rejects_unknown_keys_without_treating_lookup_as_authorization() -> None:
    with pytest.raises(UnknownDocumentTypeKey):
        document_registry.get("synthetic-unknown")

    registration = document_registry.get("synthetic-platform-test")
    assert not hasattr(registration, "template_version")
    assert not hasattr(registration, "is_available")


def test_registry_preserves_a_reviewed_disabled_state_without_implying_availability() -> None:
    registration = replace(
        document_registry.get("synthetic-platform-test"),
        enabled=False,
        english_name=None,
    )

    registry = DocumentRegistry((registration,))

    assert registry.get("synthetic-platform-test").enabled is False
    assert registry.describe()[0]["enabled"] is False


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"key": "VDS-01"}, "stable key"),
        ({"key": "vds-1"}, "stable key"),
        ({"key": "request-created"}, "stable key"),
        ({"official_code": ""}, "official code"),
        ({"vietnamese_name": ""}, "Vietnamese name"),
        ({"schema_version": ""}, "schema version"),
        ({"form_provider": None}, "form provider"),
        ({"context_mapper": None}, "context mapper"),
        ({"filename_builder": None}, "filename builder"),
        ({"minimal_fixture": None}, "minimal fixture provider"),
        ({"representative_fixture": None}, "representative fixture provider"),
    ],
)
def test_registry_rejects_invalid_or_missing_contract_members(
    changes: dict[str, object], message: str
) -> None:
    registration = document_registry.get("synthetic-platform-test")

    with pytest.raises(InvalidDocumentRegistration, match=message):
        DocumentRegistry((replace(registration, **changes),))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "registration",
    [
        cast(Any, object()),
        replace(document_registry.get("synthetic-platform-test"), enabled=cast(Any, 1)),
        replace(document_registry.get("synthetic-platform-test"), is_synthetic=cast(Any, 1)),
        replace(document_registry.get("synthetic-platform-test"), english_name=cast(Any, 1)),
    ],
)
def test_registry_rejects_untyped_registration_metadata(registration: object) -> None:
    with pytest.raises(InvalidDocumentRegistration):
        DocumentRegistry(cast(Any, (registration,)))


def test_registry_rejects_incomplete_placeholder_contracts() -> None:
    registration = document_registry.get("synthetic-platform-test")
    duplicate = PlaceholderDefinition("document.title", PlaceholderValueKind.TEXT)
    incomplete_contract = PlaceholderContract(required=(duplicate,), optional=(duplicate,))

    with pytest.raises(InvalidDocumentRegistration, match="placeholder"):
        DocumentRegistry((replace(registration, placeholder_contract=incomplete_contract),))


@pytest.mark.parametrize(
    "contract",
    [
        PlaceholderContract(
            required=cast(Any, [PlaceholderDefinition("document.title", PlaceholderValueKind.TEXT)])
        ),
        PlaceholderContract(required=(PlaceholderDefinition("document.title", cast(Any, "text")),)),
        PlaceholderContract(
            required=(PlaceholderDefinition("document.title", PlaceholderValueKind.TEXT),),
            allowed_filters=cast(Any, {"safe"}),
        ),
    ],
)
def test_registry_rejects_mutable_or_untyped_placeholder_contracts(
    contract: PlaceholderContract,
) -> None:
    registration = document_registry.get("synthetic-platform-test")

    with pytest.raises(InvalidDocumentRegistration, match="placeholder contract"):
        DocumentRegistry((replace(registration, placeholder_contract=contract),))


@pytest.mark.parametrize("value", [False, 1, Decimal("1.0"), [], {}])
def test_registry_rejects_fixture_context_values_with_the_wrong_declared_kind(
    value: object,
) -> None:
    registration = document_registry.get("synthetic-platform-test")

    with pytest.raises(InvalidDocumentRegistration, match="value kind"):
        DocumentRegistry(
            (
                replace(
                    registration,
                    context_mapper=lambda values: {"document.title": value},
                ),
            )
        )


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (PlaceholderValueKind.BOOLEAN, True),
        (PlaceholderValueKind.DATETIME, datetime(2026, 1, 2, 3, 4)),
        (PlaceholderValueKind.DATE, date(2026, 1, 2)),
        (PlaceholderValueKind.DECIMAL, Decimal("1.0")),
        (PlaceholderValueKind.INTEGER, 1),
        (PlaceholderValueKind.LIST, ("synthetic",)),
        (PlaceholderValueKind.MAPPING, {"kind": "synthetic"}),
    ],
)
def test_registry_accepts_each_declared_placeholder_value_kind(
    kind: PlaceholderValueKind, value: object
) -> None:
    registration = document_registry.get("synthetic-platform-test")
    contract = PlaceholderContract(required=(PlaceholderDefinition("document.value", kind),))

    created = DocumentRegistry(
        (
            replace(
                registration,
                placeholder_contract=contract,
                context_mapper=lambda values: {"document.value": value},
            ),
        )
    )

    assert created.get("synthetic-platform-test").placeholder_contract == contract


def test_registry_rejects_non_callable_post_processor_declarations() -> None:
    registration = document_registry.get("synthetic-platform-test")

    with pytest.raises(InvalidDocumentRegistration, match="post-processor"):
        DocumentRegistry((registration,), post_processors={"approved": cast(Any, object())})


def test_registry_rejects_undeclared_post_processors() -> None:
    registration = document_registry.get("synthetic-platform-test")

    with pytest.raises(InvalidDocumentRegistration, match="post-processor"):
        DocumentRegistry((replace(registration, post_processor_name="arbitrary.import.path"),))


def test_registry_eagerly_rejects_invalid_provider_results() -> None:
    registration = document_registry.get("synthetic-platform-test")

    with pytest.raises(InvalidDocumentRegistration, match="Django Form"):
        DocumentRegistry((replace(registration, form_provider=cast(Any, lambda: object())),))
    with pytest.raises(InvalidDocumentRegistration, match="fixture provider"):
        DocumentRegistry(
            (
                replace(
                    registration,
                    minimal_fixture=cast(Any, lambda: "not-a-mapping"),
                ),
            )
        )


def test_registry_rejects_fixtures_that_do_not_validate_required_formsets() -> None:
    registration = document_registry.get("synthetic-platform-test")

    class NotAForm:
        pass

    class RequiredRowForm(forms.Form):
        value = forms.CharField()

    required_formset = formset_factory(RequiredRowForm, min_num=1, validate_min=True)

    with pytest.raises(InvalidDocumentRegistration, match="formset"):
        DocumentRegistry(
            (
                replace(
                    registration,
                    form_provider=lambda: DocumentFormBundle(
                        form_class=registration.form_provider().form_class,
                        formset_classes=(cast(Any, required_formset),),
                    ),
                ),
            )
        )

    with pytest.raises(InvalidDocumentRegistration, match="Django Form"):
        DocumentRegistry(
            (
                replace(
                    registration,
                    form_provider=lambda: DocumentFormBundle(form_class=cast(Any, NotAForm)),
                ),
            )
        )

    with pytest.raises(InvalidDocumentRegistration, match="formset"):
        DocumentRegistry(
            (
                replace(
                    registration,
                    form_provider=lambda: DocumentFormBundle(
                        form_class=registration.form_provider().form_class,
                        formset_classes=(cast(Any, NotAForm),),
                    ),
                ),
            )
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {
                "placeholder_contract": PlaceholderContract(
                    required=(PlaceholderDefinition("Title", PlaceholderValueKind.TEXT),)
                )
            },
            "invalid name",
        ),
        (
            {
                "placeholder_contract": PlaceholderContract(
                    required=(PlaceholderDefinition("document.title", PlaceholderValueKind.TEXT),),
                    allowed_filters=frozenset({"unsafe.filter"}),
                )
            },
            "allowlist",
        ),
        ({"minimal_fixture": lambda: {}}, "fixture must satisfy"),
        ({"context_mapper": lambda values: "not-a-mapping"}, "context mapper"),
        ({"context_mapper": lambda values: {}}, "placeholder contract"),
        ({"filename_builder": lambda values: "../../unsafe.docx"}, "unsafe name"),
    ],
)
def test_registry_rejects_provider_outputs_that_break_the_contract(
    changes: dict[str, object], message: str
) -> None:
    registration = document_registry.get("synthetic-platform-test")

    with pytest.raises(InvalidDocumentRegistration, match=message):
        DocumentRegistry((replace(registration, **changes),))  # type: ignore[arg-type]


def test_registry_has_stable_non_executable_description() -> None:
    assert document_registry.describe() == (
        {
            "key": "synthetic-platform-test",
            "official_code": "SYNTHETIC-DOC",
            "vietnamese_name": "Biểu mẫu kiểm thử nền tảng",
            "english_name": "Synthetic platform test document",
            "enabled": True,
            "schema_version": "v1",
            "is_synthetic": True,
            "required_placeholders": ("document.title",),
            "optional_placeholders": ("document.notes",),
            "allowed_filters": (),
            "allowed_globals": (),
            "post_processor_name": None,
        },
    )


def test_registration_constructor_is_code_contract_not_mapping_loader() -> None:
    assert not hasattr(DocumentRegistration, "from_dict")
    assert not hasattr(DocumentRegistry, "register")
    assert not hasattr(DocumentRegistry, "load")


def test_cases_source_does_not_import_documents() -> None:
    cases_root = Path(__file__).parents[2] / "cases"
    prohibited_imports: list[str] = []

    for source_path in cases_root.rglob("*.py"):
        if "tests" in source_path.parts or "migrations" in source_path.parts:
            continue
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            else:
                continue
            prohibited_imports.extend(
                name
                for name in imports
                if name == "apps.documents" or name.startswith("apps.documents.")
            )

    assert prohibited_imports == []


def test_audit_source_does_not_import_document_models() -> None:
    audit_root = Path(__file__).parents[2] / "audit"
    prohibited_imports: list[str] = []

    for source_path in audit_root.rglob("*.py"):
        if "tests" in source_path.parts or "migrations" in source_path.parts:
            continue
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            else:
                continue
            prohibited_imports.extend(
                name
                for name in imports
                if name == "apps.documents.models" or name.startswith("apps.documents.models.")
            )

    assert prohibited_imports == []
