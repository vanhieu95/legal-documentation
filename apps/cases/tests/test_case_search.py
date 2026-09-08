from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.models import AuditEvent
from apps.cases.forms import CaseListQueryForm
from apps.cases.models import CaseParticipant, CaseRecord, Court, Entity, Representation
from apps.cases.policies import case_object_policy
from apps.cases.selectors import case_search_queryset, list_cases


@pytest.fixture
def administrator(user_factory: Callable[..., User]) -> User:
    group: Group = seed_administrator_permissions()
    user = user_factory(username="synthetic-case-search-admin")
    user.groups.add(group)
    return user


def accepted_case(
    case_factory: Callable[..., CaseRecord],
    **overrides: Any,
) -> CaseRecord:
    values: dict[str, object] = {
        "procedural_stage": CaseRecord.ProceduralStage.ACCEPTED,
        "acceptance_number": "42/2026/TLST-VDS",
        "acceptance_year": 2026,
        "acceptance_date": date(2026, 4, 15),
        "acceptance_type_code": "TLST-VDS",
    }
    values.update(overrides)
    return case_factory(**values)


def query_form(**values: object) -> CaseListQueryForm:
    return CaseListQueryForm(data=values)


def result_ids(administrator: User, **values: object) -> list[object]:
    form = query_form(**values)
    assert form.is_valid(), form.errors
    return [item.pk for item in list_cases(actor=administrator, form=form).items]


def require_postgresql_unicode_casefold(query: str) -> None:
    if any(ord(character) > 127 for character in query) and connection.vendor != "postgresql":
        pytest.skip("Vietnamese Unicode case-fold verification requires PostgreSQL.")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "stored", "query"),
    [
        ("internal_reference", "SYN-REF-ALPHA", "syn-ref-a"),
        ("acceptance_number", "77/2026/TLST-VDS", "77/2026"),
        ("acceptance_year", 2026, "2026"),
        ("acceptance_type_code", "TLST-VDS", "tlst"),
        ("matter_type", "Yêu cầu tuyên bố mất năng lực hành vi", "MẤT NĂNG LỰC"),
    ],
)
def test_searches_each_case_field_with_approved_matching(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    field: str,
    stored: object,
    query: str,
) -> None:
    require_postgresql_unicode_casefold(query)
    overrides: dict[str, object] = {field: stored}
    case = (
        accepted_case(case_factory, **overrides)
        if field.startswith("acceptance_")
        else case_factory(**overrides)
    )
    other = case_factory()

    assert result_ids(administrator, q=query) == [case.pk]
    assert other.pk not in result_ids(administrator, q=query)


@pytest.mark.django_db
@pytest.mark.parametrize("query", ["SYN-IDENTIFIER-009", "syn-identifier"])
def test_identifier_search_is_exact_or_prefix_aware(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    query: str,
) -> None:
    case = case_factory(internal_reference="SYN-IDENTIFIER-009")

    assert result_ids(administrator, q=query) == [case.pk]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("court_field", "stored", "query"),
    [
        ("full_name", "Tòa án nhân dân Thành phố Thử Nghiệm", "NHÂN DÂN THÀNH PHỐ"),
        ("code", "SYN-HCM-009", "syn-hcm"),
    ],
)
def test_searches_court_name_and_code(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    court_factory: Callable[..., Court],
    court_field: str,
    stored: str,
    query: str,
) -> None:
    require_postgresql_unicode_casefold(query)
    case = case_factory(court=court_factory(**{court_field: stored}))

    assert result_ids(administrator, q=query) == [case.pk]


@pytest.mark.django_db
def test_searches_participant_and_representative_entity_names_without_duplicates(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    require_postgresql_unicode_casefold("NGUYỄN VĂN THỬ")
    case = case_factory()
    first = CaseParticipant.objects.create(
        case=case,
        entity=entity_factory(legal_name="Nguyễn Văn Thử"),
        role=CaseParticipant.Role.REQUESTER,
    )
    CaseParticipant.objects.create(
        case=case,
        entity=entity_factory(legal_name="Nguyễn Văn Thử Hai"),
        role=CaseParticipant.Role.WITNESS,
    )
    representative = entity_factory(legal_name="Công ty Đại Diện Thử Nghiệm")
    Representation.objects.create(
        case=case,
        representative_entity=representative,
        represented_participant=first,
        representation_type=Representation.Type.AUTHORIZED,
    )

    assert result_ids(administrator, q="NGUYỄN VĂN THỬ") == [case.pk]
    assert result_ids(administrator, q="đại diện thử") == [case.pk]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("filters", "matches"),
    [
        ({"status": CaseRecord.Status.ARCHIVED}, "archived"),
        ({"procedural_stage": CaseRecord.ProceduralStage.ACCEPTED}, "accepted"),
        ({"acceptance_type_code": "TLST-VDS"}, "accepted"),
        ({"acceptance_year": 2026}, "accepted"),
        ({"acceptance_date_from": "2026-04-15"}, "accepted"),
        ({"acceptance_date_to": "2026-04-15"}, "accepted"),
        ({"archive_state": "archived"}, "archived"),
        ({"archive_state": "active"}, "accepted"),
    ],
)
def test_each_case_filter_has_an_explicit_contract(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    filters: dict[str, object],
    matches: str,
) -> None:
    accepted = accepted_case(case_factory)
    archived = case_factory(
        status=CaseRecord.Status.ARCHIVED,
        archived_by=administrator,
        archived_at=timezone.now(),
        archive_reason="Synthetic archive state",
    )
    expected = accepted if matches == "accepted" else archived

    assert result_ids(administrator, **filters) == [expected.pk]


@pytest.mark.django_db
def test_court_and_combined_filters_are_applied_together(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    court_factory: Callable[..., Court],
) -> None:
    selected_court = court_factory()
    matching = accepted_case(case_factory, court=selected_court)
    accepted_case(case_factory)
    case_factory(court=selected_court)

    assert result_ids(
        administrator,
        court=str(selected_court.pk),
        procedural_stage=CaseRecord.ProceduralStage.ACCEPTED,
        acceptance_year=2026,
        acceptance_date_from="2026-04-15",
        acceptance_date_to="2026-04-15",
        archive_state="active",
    ) == [matching.pk]


@pytest.mark.django_db
def test_acceptance_date_boundaries_are_inclusive(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    start = accepted_case(case_factory, acceptance_date=date(2026, 4, 1))
    middle = accepted_case(case_factory, acceptance_date=date(2026, 4, 15))
    end = accepted_case(case_factory, acceptance_date=date(2026, 4, 30))
    accepted_case(case_factory, acceptance_date=date(2026, 5, 1))

    assert set(
        result_ids(
            administrator,
            acceptance_date_from="2026-04-01",
            acceptance_date_to="2026-04-30",
        )
    ) == {start.pk, middle.pk, end.pk}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("sort", "first_values", "second_values"),
    [
        ("updated", {}, {}),
        ("created", {}, {}),
        (
            "acceptance_date",
            {"acceptance_date": date(2026, 1, 1)},
            {"acceptance_date": date(2026, 2, 1)},
        ),
        ("acceptance_number", {"acceptance_number": "001"}, {"acceptance_number": "002"}),
        ("court", {"court__full_name": "A Court"}, {"court__full_name": "B Court"}),
        ("matter_type", {"matter_type": "A matter"}, {"matter_type": "B matter"}),
    ],
)
def test_every_allowlisted_sort_supports_ascending_and_descending(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    court_factory: Callable[..., Court],
    sort: str,
    first_values: dict[str, object],
    second_values: dict[str, object],
) -> None:
    def build(values: dict[str, object]) -> CaseRecord:
        values = values.copy()
        court_name = values.pop("court__full_name", None)
        if court_name:
            values["court"] = court_factory(full_name=court_name)
        if sort in {"acceptance_date", "acceptance_number"}:
            return accepted_case(case_factory, **values)
        return case_factory(**values)

    first = build(first_values)
    second = build(second_values)
    if sort in {"updated", "created"}:
        field = f"{sort}_at"
        CaseRecord.objects.filter(pk=first.pk).update(
            **{field: datetime(2026, 1, 1, tzinfo=ZoneInfo("UTC"))}
        )
        CaseRecord.objects.filter(pk=second.pk).update(
            **{field: datetime(2026, 2, 1, tzinfo=ZoneInfo("UTC"))}
        )

    assert result_ids(administrator, sort=sort) == [first.pk, second.pk]
    assert result_ids(administrator, sort=f"-{sort}") == [second.pk, first.pk]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sort",
    ["court__cases", "updated_at", "-court__full_name", "?", "matter_type;DROP TABLE"],
)
def test_arbitrary_sort_fields_and_orm_traversals_are_rejected(sort: str) -> None:
    form = query_form(sort=sort)

    assert not form.is_valid()
    assert "sort" in form.errors


@pytest.mark.django_db
def test_empty_query_is_valid_but_excessive_query_is_rejected() -> None:
    assert query_form(q="").is_valid()
    assert not query_form(q="x" * 101).is_valid()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "values",
    [
        {"acceptance_date_from": "not-a-date"},
        {"acceptance_date_to": "2026-99-99"},
        {"acceptance_date_from": "2026-05-01", "acceptance_date_to": "2026-04-01"},
        {"page": 0},
        {"page": -1},
        {"page": "invalid"},
        {"page_size": 0},
        {"page_size": -1},
        {"page_size": 101},
        {"page_size": "invalid"},
    ],
)
def test_invalid_dates_pages_and_page_sizes_are_rejected(values: dict[str, object]) -> None:
    assert not query_form(**values).is_valid()


@pytest.mark.django_db
@pytest.mark.parametrize("page_size", [10, 25, 50, 100])
def test_supported_page_sizes_and_default_are_bounded(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    page_size: int,
) -> None:
    seed = case_factory(created_by=administrator, last_edited_by=administrator)
    for _ in range(29):
        case_factory(
            court=seed.court,
            created_by=administrator,
            last_edited_by=administrator,
        )

    page = list_cases(actor=administrator, form=query_form(page_size=page_size))
    default_page = list_cases(actor=administrator, form=query_form())

    assert len(page.items) == min(page_size, 30)
    assert page.page_size == page_size
    assert default_page.page_size == 25
    assert len(default_page.items) == 25


@pytest.mark.django_db
def test_pagination_is_stable_with_tied_sort_values(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    seed = case_factory(
        matter_type="Same matter",
        created_by=administrator,
        last_edited_by=administrator,
    )
    cases = [seed]
    cases.extend(
        case_factory(
            court=seed.court,
            matter_type="Same matter",
            created_by=administrator,
            last_edited_by=administrator,
        )
        for _ in range(12)
    )
    expected = [case.pk for case in sorted(cases, key=lambda item: item.pk)]

    first = result_ids(administrator, sort="matter_type", page_size=10, page=1)
    second = result_ids(administrator, sort="matter_type", page_size=10, page=2)

    assert first + second == expected
    assert len(set(first + second)) == 13


@pytest.mark.django_db
def test_selector_requires_permission_and_begins_from_object_policy_scope(
    administrator: User,
    user_factory: Callable[..., User],
    case_factory: Callable[..., CaseRecord],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visible = case_factory()
    excluded = case_factory()

    def scoped(actor: User, queryset: Any) -> Any:
        return queryset.exclude(pk=excluded.pk)

    monkeypatch.setattr(case_object_policy, "scope_queryset", scoped)

    assert result_ids(administrator) == [visible.pk]
    with pytest.raises(PermissionDenied):
        list_cases(actor=user_factory(username="synthetic-no-case-view"), form=query_form())


@pytest.mark.django_db
def test_selector_prefetches_relations_with_a_fixed_query_budget_and_no_audit(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    participant = CaseParticipant.objects.create(
        case=case,
        entity=entity_factory(legal_name="Synthetic selected participant"),
        role=CaseParticipant.Role.REQUESTER,
    )
    Representation.objects.create(
        case=case,
        representative_entity=entity_factory(legal_name="Synthetic representative"),
        represented_participant=participant,
        representation_type=Representation.Type.LEGAL,
    )
    audit_count = AuditEvent.objects.count()

    with CaptureQueriesContext(connection) as queries:
        page = list_cases(actor=administrator, form=query_form())
        selected = page.items[0]
        assert selected.court.full_name
        assert [item.entity.legal_name for item in selected.participants.all()]
        assert [item.representative_entity.legal_name for item in selected.representations.all()]

    # Three authorization queries plus count, page, and two bounded prefetches.
    assert len(queries) <= 7
    assert AuditEvent.objects.count() == audit_count


@pytest.mark.postgresql
@pytest.mark.django_db
def test_representative_postgresql_query_plan_is_inspectable(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL plan verification.")
    seed = case_factory(created_by=administrator, last_edited_by=administrator)
    for number in range(100):
        accepted_case(
            case_factory,
            internal_reference=f"SYN-PLAN-{number:06d}",
            acceptance_number=f"{number:06d}/2026/TLST-VDS",
            court=seed.court,
            created_by=administrator,
            last_edited_by=administrator,
        )
    queryset = case_search_queryset(
        actor=administrator,
        form=query_form(q="SYN-PLAN-000", acceptance_year=2026, sort="-updated"),
    )

    plan = queryset.explain(format="json", analyze=False, verbose=False)

    assert "Plan" in plan
    assert CaseRecord._meta.db_table in plan


@pytest.mark.performance
@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    os.environ.get("RUN_CASE_SCALE_TESTS") != "1",
    reason="Set RUN_CASE_SCALE_TESTS=1 for the explicit 100,000-case design-target fixture.",
)
def test_case_search_plan_at_100000_case_design_target(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("The design-target fixture requires PostgreSQL.")
    seed = case_factory()
    CaseRecord.objects.bulk_create(
        [
            CaseRecord(
                internal_reference=f"SYN-SCALE-{number:06d}",
                court=seed.court,
                matter_type="Synthetic scale matter",
                procedural_stage=CaseRecord.ProceduralStage.PRE_ACCEPTANCE,
                created_by=administrator,
                last_edited_by=administrator,
            )
            for number in range(99_999)
        ],
        batch_size=5_000,
    )
    queryset = case_search_queryset(
        actor=administrator,
        form=query_form(q="SYN-SCALE-099", archive_state="active", sort="-updated"),
    )

    plan = queryset.explain(format="json", analyze=True, buffers=True)

    assert CaseRecord.objects.count() == 100_000
    assert "Execution Time" in plan
