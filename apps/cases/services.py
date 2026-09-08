from __future__ import annotations

import uuid
from typing import cast

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F, QuerySet
from django.utils import timezone

from apps.accounts.policies import (
    ApplicationPermission,
    get_object_or_not_found,
    service_permission_required,
)
from apps.audit.actions import AuditAction, AuditTargetType
from apps.cases.audit import record_case_failure, record_case_success, record_reference_success
from apps.cases.forms import (
    CaseRecordEditForm,
    CaseRecordForm,
    CourtForm,
    EntityAddressForm,
    EntityForm,
    OfficialForm,
)
from apps.cases.models import CaseRecord, Court, Entity, EntityAddress, Official
from apps.cases.policies import ReferenceObjectPolicy, case_object_policy


class CaseRevisionConflict(Exception):
    """The submitted case revision no longer matches durable state."""


def _changed_fields(form: CourtForm | EntityForm | EntityAddressForm | OfficialForm) -> list[str]:
    return [name for name in form.changed_data if name != "is_active"]


def _require_valid(form: CourtForm | EntityForm | EntityAddressForm | OfficialForm) -> None:
    if not form.is_valid():
        raise ValueError("A valid reference form is required.")


@transaction.atomic
@service_permission_required(ApplicationPermission.ADD_CASES)
def create_case(*, actor: User, form: CaseRecordForm, correlation_id: str) -> CaseRecord:
    """Create a case from revalidated client fields and server-owned metadata."""
    rebound = CaseRecordForm(data=form.data)
    if not rebound.is_valid():
        raise ValueError("A valid case form is required.")
    case = rebound.save(commit=False)
    case.status = CaseRecord.Status.ACTIVE
    case.revision = 1
    case.created_by = actor
    case.last_edited_by = actor
    case.full_clean()
    case.save()
    record_case_success(
        actor=actor,
        action=AuditAction.CASE_CREATED,
        target_id=str(case.pk),
        correlation_id=correlation_id,
    )
    return case


@service_permission_required(ApplicationPermission.CHANGE_CASES)
def update_case(
    *,
    actor: User,
    case_id: uuid.UUID,
    form: CaseRecordEditForm,
    correlation_id: str,
) -> CaseRecord:
    """Atomically update a case only when its expected revision still matches."""
    case = get_object_or_not_found(
        actor=actor,
        permission=ApplicationPermission.CHANGE_CASES,
        queryset=CaseRecord.objects.all(),
        object_policy=case_object_policy,
        pk=case_id,
    )
    rebound = CaseRecordEditForm(data=form.data, instance=case)
    if not rebound.is_valid():
        raise ValueError("A valid case edit form is required.")

    editable_fields = tuple(CaseRecordForm.Meta.fields)
    changed_fields = [name for name in rebound.changed_data if name in editable_fields]
    updates = {name: rebound.cleaned_data[name] for name in editable_fields}
    updates.update(
        revision=F("revision") + 1,
        last_edited_by=actor,
        updated_at=timezone.now(),
    )
    expected_revision = rebound.cleaned_data["expected_revision"]

    with transaction.atomic():
        updated_count = CaseRecord.objects.filter(
            pk=case_id,
            revision=expected_revision,
        ).update(**updates)
        if updated_count == 1:
            record_case_success(
                actor=actor,
                action=AuditAction.CASE_UPDATED,
                target_id=str(case_id),
                correlation_id=correlation_id,
                changed_fields=changed_fields,
            )

    if updated_count != 1:
        record_case_failure(
            actor=actor,
            action=AuditAction.CASE_UPDATED,
            target_id=str(case_id),
            correlation_id=correlation_id,
            reason_code="revision_conflict",
        )
        raise CaseRevisionConflict
    return CaseRecord.objects.select_related("court", "created_by", "last_edited_by").get(
        pk=case_id
    )


def _get_reference[TReference: Court | Entity | EntityAddress | Official](
    *,
    actor: User,
    permission: ApplicationPermission,
    model: type[TReference],
    object_id: uuid.UUID,
) -> TReference:
    return get_object_or_not_found(
        actor=actor,
        permission=permission,
        queryset=cast(QuerySet[TReference], model._default_manager.all()),
        object_policy=ReferenceObjectPolicy[TReference](),
        pk=object_id,
    )


@transaction.atomic
@service_permission_required(ApplicationPermission.ADD_REFERENCE_ENTITIES)
def create_court(*, actor: User, form: CourtForm, correlation_id: str) -> Court:
    rebound = CourtForm(data=form.data)
    _require_valid(rebound)
    court = rebound.save()
    record_reference_success(
        actor=actor,
        action=AuditAction.REFERENCE_COURT_CREATED,
        target_type=AuditTargetType.COURT,
        target_id=str(court.pk),
        correlation_id=correlation_id,
        changed_fields=_changed_fields(rebound),
    )
    return court


@transaction.atomic
@service_permission_required(ApplicationPermission.CHANGE_REFERENCE_ENTITIES)
def update_court(
    *, actor: User, court_id: uuid.UUID, form: CourtForm, correlation_id: str
) -> Court:
    court = _get_reference(
        actor=actor,
        permission=ApplicationPermission.CHANGE_REFERENCE_ENTITIES,
        model=Court,
        object_id=court_id,
    )
    rebound = CourtForm(data=form.data, instance=court)
    _require_valid(rebound)
    court = rebound.save()
    if rebound.changed_data:
        record_reference_success(
            actor=actor,
            action=AuditAction.REFERENCE_COURT_UPDATED,
            target_type=AuditTargetType.COURT,
            target_id=str(court.pk),
            correlation_id=correlation_id,
            changed_fields=_changed_fields(rebound),
        )
    return court


@transaction.atomic
@service_permission_required(ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES)
def deactivate_court(*, actor: User, court_id: uuid.UUID, correlation_id: str) -> Court:
    court = _get_reference(
        actor=actor,
        permission=ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES,
        model=Court,
        object_id=court_id,
    )
    court = Court.objects.select_for_update().get(pk=court.pk)
    if not court.is_active:
        return court
    court.is_active = False
    court.save(update_fields=["is_active"])
    Official.objects.filter(home_court=court, is_active=True).update(is_active=False)
    record_reference_success(
        actor=actor,
        action=AuditAction.REFERENCE_COURT_DEACTIVATED,
        target_type=AuditTargetType.COURT,
        target_id=str(court.pk),
        correlation_id=correlation_id,
        changed_fields=["is_active"],
    )
    return court


@transaction.atomic
@service_permission_required(ApplicationPermission.ADD_REFERENCE_ENTITIES)
def create_entity(*, actor: User, form: EntityForm, correlation_id: str) -> Entity:
    rebound = EntityForm(data=form.data)
    _require_valid(rebound)
    entity = rebound.save()
    record_reference_success(
        actor=actor,
        action=AuditAction.REFERENCE_ENTITY_CREATED,
        target_type=AuditTargetType.ENTITY,
        target_id=str(entity.pk),
        correlation_id=correlation_id,
        changed_fields=_changed_fields(rebound),
    )
    return entity


@transaction.atomic
@service_permission_required(ApplicationPermission.CHANGE_REFERENCE_ENTITIES)
def update_entity(
    *, actor: User, entity_id: uuid.UUID, form: EntityForm, correlation_id: str
) -> Entity:
    entity = _get_reference(
        actor=actor,
        permission=ApplicationPermission.CHANGE_REFERENCE_ENTITIES,
        model=Entity,
        object_id=entity_id,
    )
    rebound = EntityForm(data=form.data, instance=entity)
    _require_valid(rebound)
    entity = rebound.save()
    if rebound.changed_data:
        record_reference_success(
            actor=actor,
            action=AuditAction.REFERENCE_ENTITY_UPDATED,
            target_type=AuditTargetType.ENTITY,
            target_id=str(entity.pk),
            correlation_id=correlation_id,
            changed_fields=_changed_fields(rebound),
        )
    return entity


@transaction.atomic
@service_permission_required(ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES)
def deactivate_entity(*, actor: User, entity_id: uuid.UUID, correlation_id: str) -> Entity:
    entity = _get_reference(
        actor=actor,
        permission=ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES,
        model=Entity,
        object_id=entity_id,
    )
    entity = Entity.objects.select_for_update().get(pk=entity.pk)
    if not entity.is_active:
        return entity
    entity.is_active = False
    entity.save(update_fields=["is_active"])
    EntityAddress.objects.filter(entity=entity, is_active=True).update(is_active=False)
    Official.objects.filter(entity=entity, is_active=True).update(is_active=False)
    record_reference_success(
        actor=actor,
        action=AuditAction.REFERENCE_ENTITY_DEACTIVATED,
        target_type=AuditTargetType.ENTITY,
        target_id=str(entity.pk),
        correlation_id=correlation_id,
        changed_fields=["is_active"],
    )
    return entity


@transaction.atomic
@service_permission_required(ApplicationPermission.ADD_REFERENCE_ENTITIES)
def create_address(*, actor: User, form: EntityAddressForm, correlation_id: str) -> EntityAddress:
    rebound = EntityAddressForm(data=form.data)
    _require_valid(rebound)
    address = rebound.save()
    record_reference_success(
        actor=actor,
        action=AuditAction.REFERENCE_ADDRESS_CREATED,
        target_type=AuditTargetType.ENTITY_ADDRESS,
        target_id=str(address.pk),
        correlation_id=correlation_id,
        changed_fields=_changed_fields(rebound),
    )
    return address


@transaction.atomic
@service_permission_required(ApplicationPermission.CHANGE_REFERENCE_ENTITIES)
def update_address(
    *, actor: User, address_id: uuid.UUID, form: EntityAddressForm, correlation_id: str
) -> EntityAddress:
    address = _get_reference(
        actor=actor,
        permission=ApplicationPermission.CHANGE_REFERENCE_ENTITIES,
        model=EntityAddress,
        object_id=address_id,
    )
    rebound = EntityAddressForm(data=form.data, instance=address)
    _require_valid(rebound)
    address = rebound.save()
    if rebound.changed_data:
        record_reference_success(
            actor=actor,
            action=AuditAction.REFERENCE_ADDRESS_UPDATED,
            target_type=AuditTargetType.ENTITY_ADDRESS,
            target_id=str(address.pk),
            correlation_id=correlation_id,
            changed_fields=_changed_fields(rebound),
        )
    return address


@transaction.atomic
@service_permission_required(ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES)
def deactivate_address(*, actor: User, address_id: uuid.UUID, correlation_id: str) -> EntityAddress:
    address = _get_reference(
        actor=actor,
        permission=ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES,
        model=EntityAddress,
        object_id=address_id,
    )
    address = EntityAddress.objects.select_for_update().get(pk=address.pk)
    if not address.is_active:
        return address
    address.is_active = False
    address.save(update_fields=["is_active"])
    record_reference_success(
        actor=actor,
        action=AuditAction.REFERENCE_ADDRESS_DEACTIVATED,
        target_type=AuditTargetType.ENTITY_ADDRESS,
        target_id=str(address.pk),
        correlation_id=correlation_id,
        changed_fields=["is_active"],
    )
    return address


@transaction.atomic
@service_permission_required(ApplicationPermission.ADD_REFERENCE_ENTITIES)
def create_official(*, actor: User, form: OfficialForm, correlation_id: str) -> Official:
    rebound = OfficialForm(data=form.data)
    _require_valid(rebound)
    official = rebound.save()
    record_reference_success(
        actor=actor,
        action=AuditAction.REFERENCE_OFFICIAL_CREATED,
        target_type=AuditTargetType.OFFICIAL,
        target_id=str(official.pk),
        correlation_id=correlation_id,
        changed_fields=_changed_fields(rebound),
    )
    return official


@transaction.atomic
@service_permission_required(ApplicationPermission.CHANGE_REFERENCE_ENTITIES)
def update_official(
    *, actor: User, official_id: uuid.UUID, form: OfficialForm, correlation_id: str
) -> Official:
    official = _get_reference(
        actor=actor,
        permission=ApplicationPermission.CHANGE_REFERENCE_ENTITIES,
        model=Official,
        object_id=official_id,
    )
    rebound = OfficialForm(data=form.data, instance=official)
    _require_valid(rebound)
    official = rebound.save()
    if rebound.changed_data:
        record_reference_success(
            actor=actor,
            action=AuditAction.REFERENCE_OFFICIAL_UPDATED,
            target_type=AuditTargetType.OFFICIAL,
            target_id=str(official.pk),
            correlation_id=correlation_id,
            changed_fields=_changed_fields(rebound),
        )
    return official


@transaction.atomic
@service_permission_required(ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES)
def deactivate_official(*, actor: User, official_id: uuid.UUID, correlation_id: str) -> Official:
    official = _get_reference(
        actor=actor,
        permission=ApplicationPermission.DEACTIVATE_REFERENCE_ENTITIES,
        model=Official,
        object_id=official_id,
    )
    official = Official.objects.select_for_update().get(pk=official.pk)
    if not official.is_active:
        return official
    official.is_active = False
    official.save(update_fields=["is_active"])
    record_reference_success(
        actor=actor,
        action=AuditAction.REFERENCE_OFFICIAL_DEACTIVATED,
        target_type=AuditTargetType.OFFICIAL,
        target_id=str(official.pk),
        correlation_id=correlation_id,
        changed_fields=["is_active"],
    )
    return official
