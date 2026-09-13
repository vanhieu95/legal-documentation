from __future__ import annotations

import ast
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import FrozenInstanceError
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied

from apps.accounts.permissions import seed_administrator_permissions
from apps.cases.document_prefill import (
    AuthorizedDocumentCase,
    authorize_document_case,
    document_case_transfer,
)
from apps.cases.models import (
    CaseOfficialAssignment,
    CaseParticipant,
    CaseRecord,
    Entity,
    EntityAddress,
    Hearing,
    Official,
    Representation,
)

pytestmark = pytest.mark.django_db


def _actor(user_factory: Callable[..., User]) -> User:
    actor = user_factory(username="synthetic-prefill-admin")
    actor.groups.add(seed_administrator_permissions())
    return actor


def test_minimal_transfer_is_typed_immutable_unicode_and_read_only(
    user_factory: Callable[..., User], case_factory: Callable[..., CaseRecord]
) -> None:
    actor = _actor(user_factory)
    case = case_factory(
        created_by=actor,
        last_edited_by=actor,
        matter_type="Yêu cầu dân sự chưa thụ lý",
    )
    before = (case.revision, case.updated_at)

    transfer = document_case_transfer(authorize_document_case(actor=actor, case_id=case.pk))

    assert transfer.case.matter_type == "Yêu cầu dân sự chưa thụ lý"
    assert transfer.case.acceptance_number == ""
    assert transfer.participants == transfer.representations == ()
    assert transfer.assignments == transfer.hearings == ()
    with pytest.raises(FrozenInstanceError):
        transfer.case.matter_type = "Mutated"  # type: ignore[misc]
    case.refresh_from_db()
    assert (case.revision, case.updated_at) == before


@pytest.mark.parametrize("role", CaseParticipant.Role.values)
def test_transfer_supports_every_core_participant_role(
    role: str,
    user_factory: Callable[..., User],
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    actor = _actor(user_factory)
    case = case_factory(created_by=actor, last_edited_by=actor)
    participant = CaseParticipant.objects.create(
        case=case,
        entity=entity_factory(legal_name=f"Người tham gia {role}"),
        role=role,
        case_address="Địa chỉ riêng của hồ sơ",
        case_contact="Liên hệ riêng của hồ sơ",
    )

    transfer = document_case_transfer(authorize_document_case(actor=actor, case_id=case.pk))

    assert transfer.participants[0].id == participant.pk
    assert transfer.participants[0].role == role
    assert transfer.participants[0].address == "Địa chỉ riêng của hồ sơ"
    assert transfer.participants[0].contact == "Liên hệ riêng của hồ sơ"


def test_complete_transfer_is_deterministic_and_prefers_case_specific_values(
    user_factory: Callable[..., User],
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    actor = _actor(user_factory)
    case = case_factory(
        created_by=actor,
        last_edited_by=actor,
        procedural_stage=CaseRecord.ProceduralStage.HEARING,
        acceptance_number="42",
        acceptance_year=2026,
        acceptance_date=date(2026, 9, 13),
        acceptance_type_code="VDS",
    )
    second_entity = entity_factory(legal_name="Bình")
    first_entity = entity_factory(legal_name="Ánh")
    EntityAddress.objects.create(
        entity=first_entity,
        kind=EntityAddress.Kind.CURRENT,
        full_address="Địa chỉ thực thể",
    )
    second = CaseParticipant.objects.create(
        case=case, entity=second_entity, role=CaseParticipant.Role.RESPONDENT, ordering=2
    )
    first = CaseParticipant.objects.create(
        case=case,
        entity=first_entity,
        role=CaseParticipant.Role.REQUESTER,
        ordering=1,
        case_address="Địa chỉ ưu tiên",
    )
    representative = entity_factory(legal_name="Đại diện Ánh", display_name="Đại diện Ánh")
    Representation.objects.create(
        case=case,
        representative_entity=representative,
        represented_participant=first,
        representation_type=Representation.Type.AUTHORIZED,
        authority_reference="SYN-AUTH-42",
    )
    official_entity = entity_factory(legal_name="Thẩm phán Trần", display_name="Thẩm phán Trần")
    official = Official.objects.create(
        entity=official_entity,
        home_court=case.court,
        title="Thẩm phán",
        position="Tòa dân sự",
    )
    CaseOfficialAssignment.objects.create(
        case=case,
        official=official,
        role=CaseOfficialAssignment.Role.PRESIDING_JUDGE,
        ordering=1,
        effective_from=date(2026, 1, 1),
    )
    later = Hearing.objects.create(
        case=case,
        instance_level=Hearing.InstanceLevel.FIRST_INSTANCE,
        scheduled_at=datetime(2026, 10, 2, 8, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        location="Phòng xử 2",
    )
    earlier = Hearing.objects.create(
        case=case,
        instance_level=Hearing.InstanceLevel.FIRST_INSTANCE,
        scheduled_at=datetime(2026, 10, 1, 8, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        location="Phòng xử 1",
    )

    transfer = document_case_transfer(authorize_document_case(actor=actor, case_id=case.pk))

    assert transfer.court.code == case.court.code
    assert [item.id for item in transfer.participants] == [first.pk, second.pk]
    assert transfer.participants[0].address == "Địa chỉ ưu tiên"
    assert transfer.representations[0].representative_name == "Đại diện Ánh"
    assert transfer.assignments[0].official_name == "Thẩm phán Trần"
    assert [item.id for item in transfer.hearings] == [earlier.pk, later.pk]


def test_transfer_has_a_fixed_query_budget_without_n_plus_one(
    user_factory: Callable[..., User],
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
    django_assert_num_queries: Callable[[int], AbstractContextManager[None]],
) -> None:
    actor = _actor(user_factory)
    case = case_factory(created_by=actor, last_edited_by=actor)
    for ordering in range(8):
        CaseParticipant.objects.create(
            case=case,
            entity=entity_factory(),
            role=CaseParticipant.Role.OTHER,
            ordering=ordering,
            is_active=ordering == 0,
        )
    context = authorize_document_case(actor=actor, case_id=case.pk)
    with django_assert_num_queries(7):
        transfer = document_case_transfer(context)
    assert len(transfer.participants) == 8


def test_authorization_context_is_required_and_archived_cases_remain_readable(
    user_factory: Callable[..., User], case_factory: Callable[..., CaseRecord]
) -> None:
    actor = user_factory(username="synthetic-prefill-denied")
    case = case_factory(created_by=actor, last_edited_by=actor)
    with pytest.raises(PermissionDenied):
        authorize_document_case(actor=actor, case_id=case.pk)
    with pytest.raises(TypeError):
        document_case_transfer(case)  # type: ignore[arg-type]

    actor.groups.add(seed_administrator_permissions())
    case.status = CaseRecord.Status.ARCHIVED
    case.archived_by = actor
    from django.utils import timezone

    case.archived_at = timezone.now()
    case.archive_reason = "Synthetic archive"
    case.save()
    transfer = document_case_transfer(authorize_document_case(actor=actor, case_id=case.pk))
    assert transfer.case.status == CaseRecord.Status.ARCHIVED


def test_forged_authorization_context_cannot_bypass_policy(
    user_factory: Callable[..., User], case_factory: Callable[..., CaseRecord]
) -> None:
    actor = user_factory(username="synthetic-prefill-forged")
    case = case_factory(created_by=actor, last_edited_by=actor)

    with pytest.raises(PermissionDenied):
        document_case_transfer(AuthorizedDocumentCase(actor=actor, case_id=case.pk))


def test_cases_application_has_no_documents_import() -> None:
    cases_root = Path(__file__).parents[1]
    for source_path in cases_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = [
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ] + [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        assert not any(
            name == "apps.documents" or name.startswith("apps.documents.") for name in imported
        )
    boundary_source = (cases_root / "document_prefill.py").read_text(encoding="utf-8")
    assert "django.core.cache" not in boundary_source
    assert "logging" not in boundary_source


def test_transfer_emits_no_sensitive_log_content(
    user_factory: Callable[..., User],
    case_factory: Callable[..., CaseRecord],
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor = _actor(user_factory)
    sensitive = "SYNTHETIC-PRIVATE-PREFILL-VALUE"
    case = case_factory(created_by=actor, last_edited_by=actor, matter_type=sensitive)
    caplog.set_level(logging.DEBUG)

    transfer = document_case_transfer(authorize_document_case(actor=actor, case_id=case.pk))

    assert transfer.case.matter_type == sensitive
    assert sensitive not in caplog.text
