from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from typing import cast

import pytest
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from apps.cases.forms import CourtForm, EntityAddressForm, EntityForm, OfficialForm
from apps.cases.models import Court, Entity, EntityAddress, Official


@pytest.mark.django_db
def test_reference_models_use_opaque_uuid_primary_keys(
    court_factory: Callable[..., Court],
    entity_factory: Callable[..., Entity],
    address_factory: Callable[..., EntityAddress],
    official_factory: Callable[..., Official],
) -> None:
    records = [court_factory(), entity_factory(), address_factory(), official_factory()]
    assert all(isinstance(record.pk, uuid.UUID) for record in records)


@pytest.mark.django_db
def test_court_preserves_vietnamese_unicode_and_stable_code_uniqueness(
    court_factory: Callable[..., Court],
) -> None:
    court = court_factory(
        code="TAND-HN-01",
        full_name="Tòa án nhân dân quận Hoàn Kiếm",
        short_name="TAND Hoàn Kiếm",
        address="Phường Tràng Tiền, quận Hoàn Kiếm, Hà Nội",
    )
    court.refresh_from_db()
    assert court.full_name == "Tòa án nhân dân quận Hoàn Kiếm"

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            court_factory(code="TAND-HN-01")


@pytest.mark.django_db
def test_court_rejects_itself_as_superior(court_factory: Callable[..., Court]) -> None:
    court = court_factory()
    court.superior_court = court
    with pytest.raises(ValidationError):
        court.full_clean()


@pytest.mark.django_db
def test_entity_kind_requires_only_its_appropriate_identifier() -> None:
    individual = Entity(
        kind=Entity.Kind.INDIVIDUAL,
        legal_name="Synthetic Individual",
        registration_number="SYN-REG-001",
    )
    organization = Entity(
        kind=Entity.Kind.ORGANIZATION,
        legal_name="Synthetic Organization",
        identity_document_number="SYN-ID-001",
    )

    with pytest.raises(ValidationError) as individual_error:
        individual.full_clean()
    with pytest.raises(ValidationError) as organization_error:
        organization.full_clean()

    assert "identity_document_number" in individual_error.value.message_dict
    assert "registration_number" in organization_error.value.message_dict


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "identity_document_number", "registration_number"),
    [
        (Entity.Kind.INDIVIDUAL, "SYN-ID-002", ""),
        (Entity.Kind.ORGANIZATION, "", "SYN-REG-002"),
    ],
)
def test_entity_kind_valid_records_pass_model_and_database_constraints(
    kind: str, identity_document_number: str, registration_number: str
) -> None:
    entity = Entity(
        kind=kind,
        legal_name="Synthetic Nguyễn Organization" if registration_number else "Nguyễn Synthetic",
        identity_document_number=identity_document_number,
        registration_number=registration_number,
    )
    entity.full_clean()
    entity.save()


@pytest.mark.django_db
def test_entity_database_rejects_kind_identifier_mismatch() -> None:
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Entity.objects.create(
                kind=Entity.Kind.INDIVIDUAL,
                legal_name="Synthetic Invalid Individual",
                identity_document_number="",
                registration_number="SYN-REG-003",
            )


@pytest.mark.django_db
def test_entity_address_supports_history_and_rejects_reversed_validity(
    entity_factory: Callable[..., Entity], address_factory: Callable[..., EntityAddress]
) -> None:
    entity = entity_factory()
    historical = address_factory(
        entity=entity,
        kind=EntityAddress.Kind.PERMANENT,
        valid_from=date(2020, 1, 1),
        valid_to=date(2022, 12, 31),
    )
    current = address_factory(
        entity=entity,
        kind=EntityAddress.Kind.CURRENT,
        valid_from=date(2023, 1, 1),
    )
    assert list(entity.addresses.order_by("valid_from")) == [historical, current]

    invalid = EntityAddress(
        entity=entity,
        kind=EntityAddress.Kind.CURRENT,
        full_address="Synthetic invalid address",
        valid_from=date(2025, 1, 2),
        valid_to=date(2025, 1, 1),
    )
    with pytest.raises(ValidationError):
        invalid.full_clean()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EntityAddress.objects.create(
                entity=entity,
                kind=EntityAddress.Kind.CURRENT,
                full_address="Synthetic invalid database address",
                valid_from=date(2025, 1, 2),
                valid_to=date(2025, 1, 1),
            )


@pytest.mark.django_db
def test_official_requires_an_individual_and_accepts_inactive_history(
    entity_factory: Callable[..., Entity], court_factory: Callable[..., Court]
) -> None:
    organization = entity_factory(
        kind=Entity.Kind.ORGANIZATION,
        identity_document_number="",
        registration_number="SYN-REG-004",
    )
    invalid = Official(
        entity=organization,
        home_court=court_factory(),
        title="Judge",
        position="Civil division",
    )
    with pytest.raises(ValidationError) as error:
        invalid.full_clean()
    assert "entity" in error.value.message_dict

    inactive_person = entity_factory(is_active=False)
    official = Official(
        entity=inactive_person,
        home_court=court_factory(is_active=False),
        title="Former Judge",
        position="Former civil division",
        is_active=False,
    )
    official.full_clean()


@pytest.mark.django_db
def test_reference_forms_enforce_boundaries_and_inactive_choices(
    court_factory: Callable[..., Court], entity_factory: Callable[..., Entity]
) -> None:
    active_court = court_factory()
    inactive_court = court_factory(is_active=False)
    active_person = entity_factory()
    inactive_person = entity_factory(is_active=False)

    court_form = CourtForm()
    official_form = OfficialForm()
    superior_field = cast("forms.ModelChoiceField[Court]", court_form.fields["superior_court"])
    official_entity_field = cast("forms.ModelChoiceField[Entity]", official_form.fields["entity"])
    home_court_field = cast("forms.ModelChoiceField[Court]", official_form.fields["home_court"])
    assert superior_field.queryset is not None
    assert official_entity_field.queryset is not None
    assert home_court_field.queryset is not None
    assert active_court in superior_field.queryset
    assert inactive_court not in superior_field.queryset
    assert active_person in official_entity_field.queryset
    assert inactive_person not in official_entity_field.queryset
    assert active_court in home_court_field.queryset
    assert inactive_court not in home_court_field.queryset

    too_long = "S" * 256
    entity_form = EntityForm(
        data={
            "kind": Entity.Kind.INDIVIDUAL,
            "legal_name": too_long,
            "display_name": "Synthetic",
            "identity_document_number": "SYN-ID-005",
            "registration_number": "",
            "is_active": True,
        }
    )
    assert not entity_form.is_valid()
    assert "legal_name" in entity_form.errors


@pytest.mark.django_db
def test_address_and_official_forms_requery_relations_as_active(
    entity_factory: Callable[..., Entity], court_factory: Callable[..., Court]
) -> None:
    inactive_entity = entity_factory(is_active=False)
    inactive_court = court_factory(is_active=False)

    address_form = EntityAddressForm(
        data={
            "entity": inactive_entity.pk,
            "kind": EntityAddress.Kind.CURRENT,
            "full_address": "Synthetic submitted address",
            "is_active": True,
        }
    )
    official_form = OfficialForm(
        data={
            "entity": inactive_entity.pk,
            "home_court": inactive_court.pk,
            "title": "Judge",
            "position": "Civil division",
            "is_active": True,
        }
    )
    assert not address_form.is_valid()
    assert "entity" in address_form.errors
    assert not official_form.is_valid()
    assert {"entity", "home_court"} <= set(official_form.errors)


@pytest.mark.django_db
def test_reference_model_indexes_exist_in_database() -> None:
    expected_fragments = {
        Court._meta.db_table: {"code", "full_name", "is_active"},
        Entity._meta.db_table: {"legal_name", "kind", "is_active"},
        EntityAddress._meta.db_table: {"entity_id", "kind", "valid_to"},
        Official._meta.db_table: {"home_court_id", "is_active"},
    }
    with connection.cursor() as cursor:
        for table_name, required_columns in expected_fragments.items():
            constraints = connection.introspection.get_constraints(cursor, table_name)
            indexed_columns = {
                column
                for details in constraints.values()
                if details["index"] or details["unique"]
                for column in details["columns"]
            }
            assert required_columns <= indexed_columns


def test_operational_admin_avoids_identity_and_registration_search_fields() -> None:
    entity_admin = admin.site._registry[Entity]
    address_admin = admin.site._registry[EntityAddress]

    assert "identity_document_number" not in entity_admin.search_fields
    assert "registration_number" not in entity_admin.search_fields
    assert "full_address" not in address_admin.search_fields
    assert {"full_address", "province", "district", "ward"} <= set(address_admin.readonly_fields)


def test_sensitive_entity_identifiers_disable_browser_autocomplete() -> None:
    form = EntityForm()

    assert form.fields["identity_document_number"].widget.attrs["autocomplete"] == "off"
    assert form.fields["registration_number"].widget.attrs["autocomplete"] == "off"
