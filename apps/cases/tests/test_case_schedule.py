from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.cases.forms import assignment_formset, hearing_formset
from apps.cases.models import CaseOfficialAssignment, CaseRecord, Hearing, Official
from apps.cases.selectors import current_case_assignments, upcoming_case_hearings


@pytest.mark.django_db
@pytest.mark.parametrize("role", CaseOfficialAssignment.Role.values)
def test_every_approved_official_role_is_valid(
    role: str,
    case_factory: Callable[..., CaseRecord],
    official_factory: Callable[..., Official],
) -> None:
    case = case_factory()
    official = official_factory(home_court=case.court)
    assignment = CaseOfficialAssignment(
        case=case,
        official=official,
        role=role,
        effective_from=date(2026, 9, 1),
    )
    assignment.full_clean()
    assignment.save()
    assert assignment.role == role


@pytest.mark.django_db
def test_assignment_ordering_and_current_selector(
    case_factory: Callable[..., CaseRecord],
    official_factory: Callable[..., Official],
) -> None:
    case = case_factory()
    historical = CaseOfficialAssignment.objects.create(
        case=case,
        official=official_factory(home_court=case.court),
        role=CaseOfficialAssignment.Role.CLERK,
        ordering=2,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 8, 31),
    )
    current = CaseOfficialAssignment.objects.create(
        case=case,
        official=official_factory(home_court=case.court),
        role=CaseOfficialAssignment.Role.JUDGE,
        ordering=1,
        effective_from=date(2026, 9, 1),
    )
    assert list(current_case_assignments(case=case, on_date=date(2026, 9, 8))) == [current]
    assert historical not in current_case_assignments(case=case, on_date=date(2026, 9, 8))


@pytest.mark.django_db
def test_assignment_rejects_dates_inactive_official_and_cross_court(
    case_factory: Callable[..., CaseRecord],
    official_factory: Callable[..., Official],
) -> None:
    case = case_factory()
    for assignment in (
        CaseOfficialAssignment(
            case=case,
            official=official_factory(home_court=case.court),
            role=CaseOfficialAssignment.Role.JUDGE,
            effective_from=date(2026, 9, 8),
            effective_to=date(2026, 9, 7),
        ),
        CaseOfficialAssignment(
            case=case,
            official=official_factory(home_court=case.court, is_active=False),
            role=CaseOfficialAssignment.Role.JUDGE,
            effective_from=date(2026, 9, 8),
        ),
        CaseOfficialAssignment(
            case=case,
            official=official_factory(),
            role=CaseOfficialAssignment.Role.JUDGE,
            effective_from=date(2026, 9, 8),
        ),
    ):
        with pytest.raises(ValidationError):
            assignment.full_clean()


@pytest.mark.django_db(transaction=True)
def test_assignment_database_constraints_reject_invalid_values(
    case_factory: Callable[..., CaseRecord],
    official_factory: Callable[..., Official],
) -> None:
    for overrides in (
        {"role": "template_only_role"},
        {"ordering": -1},
        {"effective_from": date(2026, 9, 8), "effective_to": date(2026, 9, 7)},
    ):
        case = case_factory()
        values: dict[str, object] = {
            "role": CaseOfficialAssignment.Role.JUDGE,
            "effective_from": date(2026, 9, 1),
        }
        values.update(overrides)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CaseOfficialAssignment.objects.create(
                    case=case,
                    official=official_factory(home_court=case.court),
                    **values,
                )


@pytest.mark.django_db
def test_assignment_formset_rejects_tampered_case_and_unauthorized_official(
    case_factory: Callable[..., CaseRecord],
    official_factory: Callable[..., Official],
) -> None:
    case = case_factory()
    other_case = case_factory()
    cross_court_official = official_factory(home_court=other_case.court)
    formset = assignment_formset(
        case=case,
        data={
            "assignments-TOTAL_FORMS": "1",
            "assignments-INITIAL_FORMS": "0",
            "assignments-MIN_NUM_FORMS": "0",
            "assignments-MAX_NUM_FORMS": "1000",
            "assignments-0-case": str(other_case.pk),
            "assignments-0-official": str(cross_court_official.pk),
            "assignments-0-role": CaseOfficialAssignment.Role.JUDGE,
            "assignments-0-ordering": "0",
            "assignments-0-effective_from": "2026-09-08",
        },
    )
    assert not formset.is_valid()
    assert "case" not in formset.forms[0].fields
    assert "official" in formset.forms[0].errors


@pytest.mark.django_db
def test_assignment_formset_add_reorder_and_history_preserving_removal(
    case_factory: Callable[..., CaseRecord],
    official_factory: Callable[..., Official],
) -> None:
    case = case_factory()
    existing = CaseOfficialAssignment.objects.create(
        case=case,
        official=official_factory(home_court=case.court),
        role=CaseOfficialAssignment.Role.CLERK,
        ordering=2,
        effective_from=date(2026, 9, 1),
    )
    new_official = official_factory(home_court=case.court)
    formset = assignment_formset(
        case=case,
        data={
            "assignments-TOTAL_FORMS": "2",
            "assignments-INITIAL_FORMS": "1",
            "assignments-MIN_NUM_FORMS": "0",
            "assignments-MAX_NUM_FORMS": "1000",
            "assignments-0-id": str(existing.pk),
            "assignments-0-official": str(existing.official_id),
            "assignments-0-role": existing.role,
            "assignments-0-ordering": "3",
            "assignments-0-effective_from": "2026-09-01",
            "assignments-0-DELETE": "on",
            "assignments-1-official": str(new_official.pk),
            "assignments-1-role": CaseOfficialAssignment.Role.JUDGE,
            "assignments-1-ordering": "1",
            "assignments-1-effective_from": "2026-09-08",
        },
    )
    assert formset.is_valid(), formset.errors
    formset.save()
    existing.refresh_from_db()
    assert not existing.is_active
    assert CaseOfficialAssignment.objects.get(official=new_official).ordering == 1


@pytest.mark.django_db
def test_hearing_uses_aware_utc_storage_and_ho_chi_minh_presentation(
    case_factory: Callable[..., CaseRecord],
) -> None:
    scheduled = datetime(2026, 9, 8, 8, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    hearing = Hearing.objects.create(
        case=case_factory(),
        instance_level=Hearing.InstanceLevel.FIRST_INSTANCE,
        scheduled_at=scheduled,
        location="Phòng họp thử nghiệm số 2 — Tòa án",
        status=Hearing.Status.SCHEDULED,
    )
    hearing.refresh_from_db()
    assert timezone.is_aware(hearing.scheduled_at)
    assert hearing.scheduled_at.utcoffset() == timedelta(0)
    assert hearing.scheduled_at_ho_chi_minh.hour == 8
    assert hearing.location == "Phòng họp thử nghiệm số 2 — Tòa án"
    assert timezone.is_aware(hearing.created_at)
    assert timezone.is_aware(hearing.updated_at)


def test_hearing_model_rejects_naive_datetime() -> None:
    hearing = Hearing(scheduled_at=datetime(2026, 9, 8, 8, 30))
    with pytest.raises(ValidationError):
        hearing.clean()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("field", "value"),
    (("instance_level", "cassation"), ("status", "unknown")),
)
def test_hearing_database_rejects_invalid_choices(
    field: str,
    value: str,
    case_factory: Callable[..., CaseRecord],
) -> None:
    values = {
        "case": case_factory(),
        "instance_level": Hearing.InstanceLevel.FIRST_INSTANCE,
        "scheduled_at": timezone.now(),
        "location": "Synthetic hearing room",
        "status": Hearing.Status.SCHEDULED,
    }
    values[field] = value
    with pytest.raises(IntegrityError):
        Hearing.objects.create(**values)


@pytest.mark.django_db
def test_upcoming_hearing_selector_excludes_past_and_non_scheduled(
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    now = timezone.now()
    upcoming = Hearing.objects.create(
        case=case,
        instance_level=Hearing.InstanceLevel.APPELLATE,
        scheduled_at=now + timedelta(hours=2),
        location="Synthetic room A",
        status=Hearing.Status.SCHEDULED,
    )
    Hearing.objects.create(
        case=case,
        instance_level=Hearing.InstanceLevel.FIRST_INSTANCE,
        scheduled_at=now - timedelta(hours=2),
        location="Synthetic room B",
        status=Hearing.Status.COMPLETED,
    )
    assert list(upcoming_case_hearings(case=case, from_time=now)) == [upcoming]


@pytest.mark.django_db
def test_hearing_formset_is_case_scoped_and_cancels_instead_of_deleting(
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    other_case = case_factory()
    hearing = Hearing.objects.create(
        case=case,
        instance_level=Hearing.InstanceLevel.FIRST_INSTANCE,
        scheduled_at=timezone.now() + timedelta(days=1),
        location="Synthetic room",
        status=Hearing.Status.SCHEDULED,
    )
    local_value = hearing.scheduled_at_ho_chi_minh.strftime("%Y-%m-%dT%H:%M")
    formset = hearing_formset(
        case=case,
        data={
            "hearings-TOTAL_FORMS": "1",
            "hearings-INITIAL_FORMS": "1",
            "hearings-MIN_NUM_FORMS": "0",
            "hearings-MAX_NUM_FORMS": "1000",
            "hearings-0-id": str(hearing.pk),
            "hearings-0-case": str(other_case.pk),
            "hearings-0-instance_level": hearing.instance_level,
            "hearings-0-scheduled_at": local_value,
            "hearings-0-location": hearing.location,
            "hearings-0-status": hearing.status,
            "hearings-0-DELETE": "on",
        },
    )
    assert formset.is_valid(), formset.errors
    assert "case" not in formset.forms[0].fields
    formset.save()
    hearing.refresh_from_db()
    assert hearing.status == Hearing.Status.CANCELLED


def test_schedule_schema_declares_expected_constraints_and_indexes() -> None:
    assignment_constraints = {item.name for item in CaseOfficialAssignment._meta.constraints}
    assignment_indexes = {item.name for item in CaseOfficialAssignment._meta.indexes}
    hearing_constraints = {item.name for item in Hearing._meta.constraints}
    hearing_indexes = {item.name for item in Hearing._meta.indexes}
    assert {"case_assign_role_valid", "case_assign_dates_valid"} <= assignment_constraints
    assert "case_assign_current_idx" in assignment_indexes
    assert {"case_hearing_instance_valid", "case_hearing_status_valid"} <= hearing_constraints
    assert {"case_hearing_upcoming_idx", "case_hearing_case_time_idx"} <= hearing_indexes


@pytest.mark.django_db
def test_schedule_indexes_exist_in_database() -> None:
    with connection.cursor() as cursor:
        assignment_defs = connection.introspection.get_constraints(
            cursor, CaseOfficialAssignment._meta.db_table
        )
        hearing_defs = connection.introspection.get_constraints(cursor, Hearing._meta.db_table)
    assert any(
        tuple(item["columns"]) == ("case_id", "is_active", "effective_from", "effective_to")
        for item in assignment_defs.values()
        if item["index"]
    )
    assert any(
        tuple(item["columns"]) == ("status", "scheduled_at")
        for item in hearing_defs.values()
        if item["index"]
    )


def test_schedule_strings_do_not_disclose_location_or_official() -> None:
    assignment = CaseOfficialAssignment()
    hearing = Hearing(location="Synthetic sensitive location")
    assert "Synthetic sensitive location" not in str(hearing)
    assert "None" not in str(assignment)
