from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.utils import timezone

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME, seed_administrator_permissions
from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.cases.models import (
    CaseOfficialAssignment,
    CaseParticipant,
    CaseRecord,
    Entity,
    Hearing,
    Official,
    Representation,
)
from apps.cases.services import (
    CaseRevisionConflict,
    RelationshipValidationError,
    update_case_assignments,
    update_case_hearings,
    update_case_participants,
    update_case_relationships,
    update_case_representations,
)


@pytest.fixture
def administrator(user_factory: Callable[..., User]) -> User:
    seed_administrator_permissions()
    user = user_factory(username="synthetic-relationship-admin")
    user.groups.add(Group.objects.get(name=ADMINISTRATOR_GROUP_NAME))
    return user


def management(prefix: str, total: int = 1, initial: int = 0) -> dict[str, str]:
    return {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


@pytest.mark.django_db
def test_explicit_relationship_services_create_each_category_atomically(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
    official_factory: Callable[..., Official],
) -> None:
    case = case_factory()
    participant_entity = entity_factory(legal_name="Synthetic participant")
    representative = entity_factory(legal_name="Synthetic representative")
    official = official_factory(home_court=case.court)

    update_case_participants(
        actor=administrator,
        case_id=case.pk,
        expected_revision=1,
        data={
            **management("participants"),
            "participants-0-entity": str(participant_entity.pk),
            "participants-0-role": CaseParticipant.Role.REQUESTER,
            "participants-0-ordering": "2",
        },
        correlation_id="synthetic-participant-update",
    )
    participant = CaseParticipant.objects.get(case=case)
    update_case_representations(
        actor=administrator,
        case_id=case.pk,
        expected_revision=2,
        data={
            **management("representations"),
            "representations-0-representative_entity": str(representative.pk),
            "representations-0-represented_participant": str(participant.pk),
            "representations-0-representation_type": Representation.Type.AUTHORIZED,
        },
        correlation_id="synthetic-representation-update",
    )
    update_case_assignments(
        actor=administrator,
        case_id=case.pk,
        expected_revision=3,
        data={
            **management("assignments"),
            "assignments-0-official": str(official.pk),
            "assignments-0-role": CaseOfficialAssignment.Role.JUDGE,
            "assignments-0-ordering": "1",
            "assignments-0-effective_from": "2026-09-09",
        },
        correlation_id="synthetic-assignment-update",
    )
    update_case_hearings(
        actor=administrator,
        case_id=case.pk,
        expected_revision=4,
        data={
            **management("hearings"),
            "hearings-0-instance_level": Hearing.InstanceLevel.FIRST_INSTANCE,
            "hearings-0-scheduled_at": "2026-09-10T08:30",
            "hearings-0-location": "Synthetic room\nSecond line",
            "hearings-0-status": Hearing.Status.SCHEDULED,
        },
        correlation_id="synthetic-hearing-update",
    )

    case.refresh_from_db()
    assert case.revision == 5
    assert Representation.objects.filter(case=case).count() == 1
    assert CaseOfficialAssignment.objects.filter(case=case).count() == 1
    assert Hearing.objects.get(case=case).scheduled_at.tzinfo is not None
    events = AuditEvent.objects.filter(action=AuditAction.CASE_RELATIONSHIPS_UPDATED)
    assert events.count() == 4
    assert all("Synthetic" not in str(event.metadata) for event in events)


@pytest.mark.django_db
def test_invalid_formset_rolls_back_every_relationship_and_revision(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    entity = entity_factory()
    data = {
        **management("participants"),
        **management("representations", total=0),
        **management("assignments", total=0),
        **management("hearings"),
        "participants-0-entity": str(entity.pk),
        "participants-0-role": CaseParticipant.Role.REQUESTER,
        "participants-0-ordering": "0",
        "hearings-0-instance_level": Hearing.InstanceLevel.FIRST_INSTANCE,
        "hearings-0-scheduled_at": "not-a-date",
        "hearings-0-location": "Synthetic room",
        "hearings-0-status": Hearing.Status.SCHEDULED,
    }

    with pytest.raises(RelationshipValidationError) as caught:
        update_case_relationships(
            actor=administrator,
            case_id=case.pk,
            expected_revision=case.revision,
            data=data,
            correlation_id="synthetic-invalid-combined",
        )

    case.refresh_from_db()
    assert case.revision == 1
    assert not CaseParticipant.objects.filter(case=case).exists()
    assert not Hearing.objects.filter(case=case).exists()
    assert caught.value.formsets["hearings"].forms[0]["scheduled_at"].errors
    failure = AuditEvent.objects.get(action=AuditAction.CASE_RELATIONSHIPS_UPDATED)
    assert failure.outcome == "failure"
    assert failure.metadata == {
        "reason_code": "validation_error",
        "relationship_categories": [
            "assignments",
            "hearings",
            "participants",
            "representations",
        ],
    }


@pytest.mark.django_db
def test_combined_update_commits_all_formsets_with_one_revision_increment(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
    official_factory: Callable[..., Official],
) -> None:
    case = case_factory()
    participant = CaseParticipant.objects.create(
        case=case,
        entity=entity_factory(),
        role=CaseParticipant.Role.REQUESTER,
    )
    representative = entity_factory()
    official = official_factory(home_court=case.court)
    data = {
        **management("participants", initial=1),
        **management("representations"),
        **management("assignments"),
        **management("hearings"),
        "participants-0-id": str(participant.pk),
        "participants-0-entity": str(participant.entity_id),
        "participants-0-role": participant.role,
        "participants-0-ordering": "4",
        "representations-0-representative_entity": str(representative.pk),
        "representations-0-represented_participant": str(participant.pk),
        "representations-0-representation_type": Representation.Type.LEGAL,
        "representations-0-description": "Dòng một\nDòng hai có dấu",
        "assignments-0-official": str(official.pk),
        "assignments-0-role": CaseOfficialAssignment.Role.CLERK,
        "assignments-0-ordering": "2",
        "assignments-0-effective_from": "2026-09-09",
        "hearings-0-instance_level": Hearing.InstanceLevel.APPELLATE,
        "hearings-0-scheduled_at": "2026-09-11T09:45",
        "hearings-0-location": "Phòng xử án thử nghiệm",
        "hearings-0-status": Hearing.Status.SCHEDULED,
    }

    updated = update_case_relationships(
        actor=administrator,
        case_id=case.pk,
        expected_revision=1,
        data=data,
        correlation_id="synthetic-valid-combined",
    )

    participant.refresh_from_db()
    assert updated.revision == 2
    assert participant.ordering == 4
    assert Representation.objects.get(case=case).description == "Dòng một\nDòng hai có dấu"
    assert CaseOfficialAssignment.objects.filter(case=case).count() == 1
    assert Hearing.objects.filter(case=case).count() == 1
    event = AuditEvent.objects.get(action=AuditAction.CASE_RELATIONSHIPS_UPDATED)
    assert event.changed_fields == ["assignments", "hearings", "participants", "representations"]
    assert event.metadata == {
        "relationship_categories": [
            "assignments",
            "hearings",
            "participants",
            "representations",
        ]
    }


@pytest.mark.django_db
@pytest.mark.parametrize("tamper", ["missing-management", "duplicate", "inactive", "cross-case"])
def test_participant_service_rejects_tampering_without_writes(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
    tamper: str,
) -> None:
    case = case_factory()
    entity = entity_factory(is_active=tamper != "inactive")
    data = {
        **management("participants", total=2 if tamper == "duplicate" else 1),
        "participants-0-entity": str(entity.pk),
        "participants-0-role": CaseParticipant.Role.REQUESTER,
        "participants-0-ordering": "0",
    }
    if tamper == "missing-management":
        data.pop("participants-TOTAL_FORMS")
    elif tamper == "duplicate":
        data.update(
            {
                "participants-1-entity": str(entity.pk),
                "participants-1-role": CaseParticipant.Role.REQUESTER,
                "participants-1-ordering": "1",
            }
        )
    elif tamper == "cross-case":
        other = CaseParticipant.objects.create(
            case=case_factory(),
            entity=entity,
            role=CaseParticipant.Role.REQUESTER,
        )
        data.update(
            {
                "participants-INITIAL_FORMS": "1",
                "participants-0-id": str(other.pk),
            }
        )

    with pytest.raises(RelationshipValidationError):
        update_case_participants(
            actor=administrator,
            case_id=case.pk,
            expected_revision=1,
            data=data,
            correlation_id=f"synthetic-{tamper}",
        )

    case.refresh_from_db()
    assert case.revision == 1
    assert not CaseParticipant.objects.filter(case=case).exists()


@pytest.mark.django_db
def test_service_removals_preserve_participant_and_hearing_history(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory()
    participant = CaseParticipant.objects.create(
        case=case,
        entity=entity_factory(),
        role=CaseParticipant.Role.REQUESTER,
    )
    hearing = Hearing.objects.create(
        case=case,
        instance_level=Hearing.InstanceLevel.FIRST_INSTANCE,
        scheduled_at=timezone.now(),
        location="Synthetic hearing room",
        status=Hearing.Status.SCHEDULED,
    )
    participant_data = {
        **management("participants", initial=1),
        "participants-0-id": str(participant.pk),
        "participants-0-entity": str(participant.entity_id),
        "participants-0-role": participant.role,
        "participants-0-ordering": "0",
        "participants-0-DELETE": "on",
    }
    update_case_participants(
        actor=administrator,
        case_id=case.pk,
        expected_revision=1,
        data=participant_data,
        correlation_id="synthetic-remove-participant",
    )
    local_time = hearing.scheduled_at_ho_chi_minh.strftime("%Y-%m-%dT%H:%M")
    hearing_data = {
        **management("hearings", initial=1),
        "hearings-0-id": str(hearing.pk),
        "hearings-0-instance_level": hearing.instance_level,
        "hearings-0-scheduled_at": local_time,
        "hearings-0-location": hearing.location,
        "hearings-0-status": hearing.status,
        "hearings-0-DELETE": "on",
    }
    update_case_hearings(
        actor=administrator,
        case_id=case.pk,
        expected_revision=2,
        data=hearing_data,
        correlation_id="synthetic-remove-hearing",
    )

    participant.refresh_from_db()
    hearing.refresh_from_db()
    assert not participant.is_active
    assert hearing.status == Hearing.Status.CANCELLED
    assert CaseParticipant.objects.filter(pk=participant.pk).exists()
    assert Hearing.objects.filter(pk=hearing.pk).exists()


@pytest.mark.django_db
def test_stale_and_unprivileged_relationship_updates_write_nothing(
    administrator: User,
    user_factory: Callable[..., User],
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    case = case_factory(revision=2, updated_at=timezone.now())
    entity = entity_factory()
    data = {
        **management("participants"),
        "participants-0-entity": str(entity.pk),
        "participants-0-role": CaseParticipant.Role.REQUESTER,
        "participants-0-ordering": "0",
    }

    with pytest.raises(CaseRevisionConflict):
        update_case_participants(
            actor=administrator,
            case_id=case.pk,
            expected_revision=1,
            data=data,
            correlation_id="synthetic-stale",
        )
    with pytest.raises(PermissionDenied):
        update_case_participants(
            actor=user_factory(),
            case_id=case.pk,
            expected_revision=2,
            data=data,
            correlation_id="synthetic-denied",
        )

    assert not CaseParticipant.objects.filter(case=case).exists()
    assert not AuditEvent.objects.filter(
        action=AuditAction.CASE_RELATIONSHIPS_UPDATED, outcome="success"
    ).exists()


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_relationship_updates_allow_one_revision_winner(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    entity_factory: Callable[..., Entity],
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL concurrency profile.")
    case = case_factory()
    entities = (entity_factory(), entity_factory())
    barrier = Barrier(2)

    def submit(entity_id: object) -> str:
        close_old_connections()
        actor = User.objects.get(pk=administrator.pk)
        data = {
            **management("participants"),
            "participants-0-entity": str(entity_id),
            "participants-0-role": CaseParticipant.Role.REQUESTER,
            "participants-0-ordering": "0",
        }
        barrier.wait()
        try:
            update_case_participants(
                actor=actor,
                case_id=case.pk,
                expected_revision=1,
                data=data,
                correlation_id=f"synthetic-concurrent-{entity_id}",
            )
        except CaseRevisionConflict:
            return "conflict"
        finally:
            close_old_connections()
        return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, (entities[0].pk, entities[1].pk)))

    assert sorted(outcomes) == ["conflict", "success"]
    case.refresh_from_db()
    assert case.revision == 2
    assert CaseParticipant.objects.filter(case=case).count() == 1
