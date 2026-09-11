from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from apps.cases.forms import participant_formset, representation_formset
from apps.cases.models import CaseParticipant, CaseRecord, Entity, Representation


@pytest.mark.django_db
@pytest.mark.parametrize("role", CaseParticipant.Role.values)
def test_every_approved_participant_role_is_valid(
    role: str,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    participant = CaseParticipant(case=case_factory(), entity=entity_factory(), role=role)
    participant.full_clean()
    participant.save()
    assert participant.role == role


@pytest.mark.django_db
def test_participants_are_ordered_and_allow_multiple_distinct_roles(
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    entity = entity_factory()
    second = CaseParticipant.objects.create(
        case=case, entity=entity, role=CaseParticipant.Role.WITNESS, ordering=2
    )
    first = CaseParticipant.objects.create(
        case=case, entity=entity, role=CaseParticipant.Role.REQUESTER, ordering=1
    )
    assert list(case.participants.all()) == [first, second]


@pytest.mark.django_db(transaction=True)
def test_duplicate_active_identical_role_is_rejected_but_history_is_allowed(
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    entity = entity_factory()
    CaseParticipant.objects.create(case=case, entity=entity, role=CaseParticipant.Role.REQUESTER)
    with pytest.raises(IntegrityError):
        CaseParticipant.objects.create(
            case=case, entity=entity, role=CaseParticipant.Role.REQUESTER
        )
    CaseParticipant.objects.filter(case=case, entity=entity).update(is_active=False)
    historical = CaseParticipant.objects.create(
        case=case, entity=entity, role=CaseParticipant.Role.REQUESTER
    )
    assert historical.is_active


@pytest.mark.django_db
def test_case_specific_text_preserves_unicode_and_line_breaks(
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    participant = CaseParticipant.objects.create(
        case=case_factory(),
        entity=entity_factory(),
        role=CaseParticipant.Role.RELATED_PARTY,
        case_address="Số 1, đường Hòa Bình\nPhường Minh Khai",
        case_workplace="Công ty thử nghiệm Ánh Dương",
        case_contact="Kênh liên hệ thứ nhất\nKênh liên hệ thứ hai",
    )
    participant.refresh_from_db()
    assert participant.case_address == "Số 1, đường Hòa Bình\nPhường Minh Khai"
    assert participant.case_contact.count("\n") == 1


@pytest.mark.django_db
def test_participant_effective_date_range_is_validated(
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    invalid = CaseParticipant(
        case=case_factory(),
        entity=entity_factory(),
        role=CaseParticipant.Role.EXPERT,
        effective_from=date(2026, 9, 8),
        effective_to=date(2026, 9, 7),
    )
    with pytest.raises(ValidationError):
        invalid.full_clean()


@pytest.mark.django_db(transaction=True)
def test_participant_constraints_reject_invalid_role_order_and_date_range(
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    for overrides in (
        {"role": "template_only_role"},
        {"ordering": -1},
        {"effective_from": date(2026, 9, 8), "effective_to": date(2026, 9, 7)},
    ):
        values: dict[str, object] = {"role": CaseParticipant.Role.OTHER}
        values.update(overrides)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CaseParticipant.objects.create(
                    case=case_factory(),
                    entity=entity_factory(),
                    **values,
                )


@pytest.mark.django_db
def test_representation_requires_participant_from_same_case(
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    participant = CaseParticipant.objects.create(
        case=case,
        entity=entity_factory(),
        role=CaseParticipant.Role.REQUESTER,
    )
    representation = Representation(
        case=case,
        representative_entity=entity_factory(),
        represented_participant=participant,
        representation_type=Representation.Type.AUTHORIZED,
        authority_reference="SYN-AUTH-001",
        authority_date=date(2026, 9, 7),
        description="Phạm vi đại diện thử nghiệm",
    )
    representation.full_clean()
    representation.save()
    representation.refresh_from_db()
    assert representation.description == "Phạm vi đại diện thử nghiệm"

    representation.case = case_factory()
    with pytest.raises(ValidationError):
        representation.full_clean()


@pytest.mark.django_db
def test_relationship_forms_scope_relational_choices_and_ignore_posted_case(
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    other_case = case_factory()
    active_entity = entity_factory()
    inactive_entity = entity_factory(is_active=False)
    other_participant = CaseParticipant.objects.create(
        case=other_case,
        entity=active_entity,
        role=CaseParticipant.Role.REQUESTER,
    )

    participant_set = participant_formset(
        case=case,
        data={
            "participants-TOTAL_FORMS": "1",
            "participants-INITIAL_FORMS": "0",
            "participants-MIN_NUM_FORMS": "0",
            "participants-MAX_NUM_FORMS": "1000",
            "participants-0-case": str(other_case.pk),
            "participants-0-entity": str(inactive_entity.pk),
            "participants-0-role": CaseParticipant.Role.REQUESTER,
            "participants-0-ordering": "0",
        },
    )
    assert not participant_set.is_valid()
    assert "case" not in participant_set.forms[0].fields
    assert "entity" in participant_set.forms[0].errors

    representation_set = representation_formset(
        case=case,
        data={
            "representations-TOTAL_FORMS": "1",
            "representations-INITIAL_FORMS": "0",
            "representations-MIN_NUM_FORMS": "0",
            "representations-MAX_NUM_FORMS": "1000",
            "representations-0-case": str(other_case.pk),
            "representations-0-representative_entity": str(active_entity.pk),
            "representations-0-represented_participant": str(other_participant.pk),
            "representations-0-representation_type": Representation.Type.LEGAL,
        },
    )
    assert not representation_set.is_valid()
    assert "case" not in representation_set.forms[0].fields
    assert "represented_participant" in representation_set.forms[0].errors


@pytest.mark.django_db
def test_participant_formset_add_update_reorder_and_history_preserving_removal(
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    existing = CaseParticipant.objects.create(
        case=case,
        entity=entity_factory(),
        role=CaseParticipant.Role.REQUESTER,
        ordering=1,
    )
    added_entity = entity_factory()
    formset = participant_formset(
        case=case,
        data={
            "participants-TOTAL_FORMS": "2",
            "participants-INITIAL_FORMS": "1",
            "participants-MIN_NUM_FORMS": "0",
            "participants-MAX_NUM_FORMS": "1000",
            "participants-0-id": str(existing.pk),
            "participants-0-entity": str(existing.entity_id),
            "participants-0-role": existing.role,
            "participants-0-ordering": "3",
            "participants-0-DELETE": "on",
            "participants-1-entity": str(added_entity.pk),
            "participants-1-role": CaseParticipant.Role.WITNESS,
            "participants-1-ordering": "1",
        },
    )
    assert formset.is_valid(), formset.errors
    formset.save()
    existing.refresh_from_db()
    added = CaseParticipant.objects.get(case=case, entity=added_entity)
    assert not existing.is_active
    assert added.ordering == 1
    assert CaseParticipant.objects.filter(pk=existing.pk).exists()


@pytest.mark.django_db
def test_representation_formset_add_and_history_preserving_removal(
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    participant = CaseParticipant.objects.create(
        case=case, entity=entity_factory(), role=CaseParticipant.Role.RESPONDENT
    )
    representation = Representation.objects.create(
        case=case,
        representative_entity=entity_factory(),
        represented_participant=participant,
        representation_type=Representation.Type.LEGAL,
    )
    formset = representation_formset(
        case=case,
        data={
            "representations-TOTAL_FORMS": "1",
            "representations-INITIAL_FORMS": "1",
            "representations-MIN_NUM_FORMS": "0",
            "representations-MAX_NUM_FORMS": "1000",
            "representations-0-id": str(representation.pk),
            "representations-0-representative_entity": str(representation.representative_entity_id),
            "representations-0-represented_participant": str(participant.pk),
            "representations-0-representation_type": representation.representation_type,
            "representations-0-DELETE": "on",
        },
    )
    assert formset.is_valid(), formset.errors
    formset.save()
    representation.refresh_from_db()
    assert not representation.is_active


def test_relationship_schema_declares_expected_constraints_and_indexes() -> None:
    participant_constraints = {item.name for item in CaseParticipant._meta.constraints}
    representation_constraints = {item.name for item in Representation._meta.constraints}
    participant_indexes = {item.name for item in CaseParticipant._meta.indexes}
    representation_indexes = {item.name for item in Representation._meta.indexes}
    assert {"case_part_active_role_uniq", "case_part_dates_valid"} <= (participant_constraints)
    assert "case_repr_case_part_idx" in representation_indexes
    assert "case_part_role_order_idx" in participant_indexes
    assert "case_repr_active_unique" in representation_constraints


@pytest.mark.django_db
def test_relationship_indexes_exist_in_database() -> None:
    with connection.cursor() as cursor:
        participant_definitions = connection.introspection.get_constraints(
            cursor, CaseParticipant._meta.db_table
        )
        representation_definitions = connection.introspection.get_constraints(
            cursor, Representation._meta.db_table
        )
    assert any(
        tuple(item["columns"]) == ("case_id", "role", "ordering")
        for item in participant_definitions.values()
        if item["index"]
    )
    assert any(
        tuple(item["columns"]) == ("case_id", "represented_participant_id")
        for item in representation_definitions.values()
        if item["index"]
    )


def test_relationship_strings_do_not_disclose_personal_data() -> None:
    participant = CaseParticipant()
    representation = Representation()
    assert "None" not in str(participant)
    assert "None" not in str(representation)
