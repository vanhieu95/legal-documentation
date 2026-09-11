from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, datetime
from itertools import combinations

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.cases.forms import CaseRecordForm
from apps.cases.models import CaseRecord, Court

ACCEPTANCE_FIELD_VALUES: dict[str, object] = {
    "acceptance_number": "42",
    "acceptance_year": 2026,
    "acceptance_date": date(2026, 9, 7),
    "acceptance_type_code": "VDS",
}
PARTIAL_ACCEPTANCE_GROUPS = [
    dict(combination)
    for size in range(1, len(ACCEPTANCE_FIELD_VALUES))
    for combination in combinations(ACCEPTANCE_FIELD_VALUES.items(), size)
]


def case_values(*, court: Court, actor: User, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "internal_reference": f"SYN-CASE-{uuid.uuid4().hex[:12]}",
        "court": court,
        "matter_type": "Synthetic civil matter",
        "procedural_stage": CaseRecord.ProceduralStage.PRE_ACCEPTANCE,
        "created_by": actor,
        "last_edited_by": actor,
    }
    values.update(overrides)
    return values


@pytest.mark.django_db
def test_incomplete_pre_acceptance_case_is_valid(
    court_factory: Callable[..., Court], user_factory: Callable[..., User]
) -> None:
    record = CaseRecord(**case_values(court=court_factory(), actor=user_factory()))

    record.full_clean()
    record.save()

    assert isinstance(record.pk, uuid.UUID)
    assert record.revision == 1
    assert record.status == CaseRecord.Status.ACTIVE
    assert record.acceptance_number == ""
    assert record.acceptance_year is None
    assert record.acceptance_date is None
    assert record.acceptance_type_code == ""


@pytest.mark.django_db
def test_accepted_case_with_complete_acceptance_group_is_valid(
    court_factory: Callable[..., Court], user_factory: Callable[..., User]
) -> None:
    record = CaseRecord(
        **case_values(
            court=court_factory(),
            actor=user_factory(),
            matter_type="Yêu cầu công nhận kết quả hòa giải thành ngoài Tòa án",
            procedural_stage=CaseRecord.ProceduralStage.ACCEPTED,
            acceptance_number="42",
            acceptance_year=2026,
            acceptance_date=date(2026, 9, 7),
            acceptance_type_code="VDS",
        )
    )

    record.full_clean()
    record.save()
    record.refresh_from_db()

    assert record.matter_type == "Yêu cầu công nhận kết quả hòa giải thành ngoài Tòa án"
    assert isinstance(record.acceptance_date, date)
    assert not isinstance(record.acceptance_date, datetime)
    assert timezone.is_aware(record.created_at)
    assert timezone.is_aware(record.updated_at)


@pytest.mark.django_db
@pytest.mark.parametrize("partial_group", PARTIAL_ACCEPTANCE_GROUPS)
def test_model_rejects_every_partial_accepted_group(
    partial_group: dict[str, object],
    court_factory: Callable[..., Court],
    user_factory: Callable[..., User],
) -> None:
    record = CaseRecord(
        **case_values(
            court=court_factory(),
            actor=user_factory(),
            procedural_stage=CaseRecord.ProceduralStage.ACCEPTED,
            **partial_group,
        )
    )

    with pytest.raises(ValidationError):
        record.full_clean()


@pytest.mark.django_db
def test_form_rejects_partial_acceptance_group_and_excludes_controlled_metadata(
    court_factory: Callable[..., Court], user_factory: Callable[..., User]
) -> None:
    court = court_factory()
    form = CaseRecordForm(
        data={
            "internal_reference": "SYN-CASE-FORM-001",
            "court": court.pk,
            "matter_type": "Synthetic accepted matter",
            "procedural_stage": CaseRecord.ProceduralStage.ACCEPTED,
            "acceptance_number": "42",
            "acceptance_year": "2026",
            "acceptance_date": "2026-09-07",
            "acceptance_type_code": "",
            "revision": "999",
            "created_by": user_factory().pk,
        }
    )

    assert not form.is_valid()
    assert "acceptance_type_code" in form.errors
    assert {
        "revision",
        "created_by",
        "last_edited_by",
        "status",
        "archived_by",
        "archived_at",
        "archive_reason",
    }.isdisjoint(form.fields)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("partial_group", PARTIAL_ACCEPTANCE_GROUPS)
def test_database_rejects_every_partial_accepted_group(
    partial_group: dict[str, object],
    court_factory: Callable[..., Court],
    user_factory: Callable[..., User],
) -> None:
    with pytest.raises(IntegrityError):
        CaseRecord.objects.create(
            **case_values(
                court=court_factory(),
                actor=user_factory(),
                procedural_stage=CaseRecord.ProceduralStage.ACCEPTED,
                **partial_group,
            )
        )


@pytest.mark.django_db
def test_internal_reference_is_unique_and_bounded(
    court_factory: Callable[..., Court], user_factory: Callable[..., User]
) -> None:
    values = case_values(court=court_factory(), actor=user_factory())
    CaseRecord.objects.create(**values)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CaseRecord.objects.create(**values)

    too_long = CaseRecord(
        **case_values(
            court=court_factory(),
            actor=user_factory(username="synthetic-boundary-user"),
            internal_reference="R" * 65,
        )
    )
    with pytest.raises(ValidationError):
        too_long.full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field_name", "maximum"),
    (
        ("internal_reference", 64),
        ("matter_type", 255),
        ("acceptance_number", 64),
        ("acceptance_type_code", 32),
        ("archive_reason", 500),
    ),
)
def test_case_record_text_field_boundaries(
    field_name: str,
    maximum: int,
    court_factory: Callable[..., Court],
    user_factory: Callable[..., User],
) -> None:
    actor = user_factory()
    record = CaseRecord(**case_values(court=court_factory(), actor=actor))
    setattr(record, field_name, "S" * (maximum + 1))

    with pytest.raises(ValidationError) as error:
        record.full_clean()

    assert field_name in error.value.message_dict


@pytest.mark.django_db
def test_revision_and_archive_metadata_constraints(
    court_factory: Callable[..., Court], user_factory: Callable[..., User]
) -> None:
    actor = user_factory()
    court = court_factory()
    invalid_revision = CaseRecord(**case_values(court=court, actor=actor, revision=0))
    with pytest.raises(ValidationError):
        invalid_revision.full_clean()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CaseRecord.objects.create(**case_values(court=court, actor=actor, revision=0))

    incomplete_archive = CaseRecord(
        **case_values(court=court, actor=actor, status=CaseRecord.Status.ARCHIVED)
    )
    with pytest.raises(ValidationError):
        incomplete_archive.full_clean()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CaseRecord.objects.create(
                **case_values(court=court, actor=actor, status=CaseRecord.Status.ARCHIVED)
            )

    archived = CaseRecord(
        **case_values(
            court=court,
            actor=actor,
            status=CaseRecord.Status.ARCHIVED,
            archived_by=actor,
            archived_at=timezone.now(),
            archive_reason="Synthetic retention-safe reason",
        )
    )
    archived.full_clean()
    archived.save()
    assert archived.archived_at is not None
    assert timezone.is_aware(archived.archived_at)


@pytest.mark.django_db
def test_creator_and_editor_are_required_and_protected(
    court_factory: Callable[..., Court], user_factory: Callable[..., User]
) -> None:
    actor = user_factory()
    record = CaseRecord(**case_values(court=court_factory(), actor=actor))
    record.full_clean()
    record.save()

    assert record.created_by == actor
    assert record.last_edited_by == actor
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CaseRecord.objects.create(
                internal_reference="SYN-CASE-NO-ACTOR",
                court=court_factory(),
                matter_type="Synthetic matter",
                procedural_stage=CaseRecord.ProceduralStage.PRE_ACCEPTANCE,
            )


def test_case_record_schema_declares_expected_constraints_and_indexes() -> None:
    constraint_names = {constraint.name for constraint in CaseRecord._meta.constraints}
    index_names = {index.name for index in CaseRecord._meta.indexes}

    assert {
        "case_record_acceptance_group_valid",
        "case_record_revision_positive",
        "case_record_archive_metadata_valid",
    } <= constraint_names
    assert {
        "case_record_state_stage_idx",
        "case_record_court_state_idx",
        "case_record_acceptance_idx",
        "case_record_updated_idx",
    } <= index_names


@pytest.mark.django_db
def test_case_record_indexes_exist_in_database() -> None:
    with connection.cursor() as cursor:
        definitions = connection.introspection.get_constraints(cursor, CaseRecord._meta.db_table)
    indexed_columns = {
        tuple(details["columns"])
        for details in definitions.values()
        if details["index"] or details["unique"]
    }
    assert ("status", "procedural_stage") in indexed_columns
    assert ("court_id", "status") in indexed_columns
    assert ("acceptance_year", "acceptance_type_code", "acceptance_date") in indexed_columns
    assert ("updated_at",) in indexed_columns


def test_case_record_string_does_not_disclose_case_details() -> None:
    record = CaseRecord(
        internal_reference="SYN-SENSITIVE-REFERENCE",
        matter_type="Synthetic sensitive legal detail",
    )

    rendered = str(record)

    assert "SYN-SENSITIVE-REFERENCE" not in rendered
    assert "Synthetic sensitive legal detail" not in rendered


def test_case_admin_does_not_search_or_list_legal_case_details() -> None:
    from django.contrib import admin

    case_admin = admin.site._registry[CaseRecord]
    exposed_fields = set(case_admin.list_display) | set(case_admin.search_fields)

    assert {
        "internal_reference",
        "matter_type",
        "acceptance_number",
        "archive_reason",
    }.isdisjoint(exposed_fields)
