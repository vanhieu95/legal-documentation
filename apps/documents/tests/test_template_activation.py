from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import UUID

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import close_old_connections, connection

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.actions import AuditAction, AuditOutcome
from apps.audit.models import AuditEvent
from apps.documents.models import TemplateVersion
from apps.documents.selectors import get_active_template
from apps.documents.services import (
    TemplateTransitionConflict,
    activate_template_version,
    deactivate_template_version,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _isolated_private_storage(settings: Any, tmp_path: Path) -> None:
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"
    storages._storages.clear()  # type: ignore[attr-defined]


def _actor(user_factory: object, username: str = "synthetic-activation-admin") -> User:
    actor = user_factory(username=username)  # type: ignore[operator]
    actor.groups.add(seed_administrator_permissions())
    return actor


def _version(actor: User, version: str, *, valid: bool = True) -> TemplateVersion:
    template = TemplateVersion.objects.create(
        type_key="synthetic-platform-test",
        version=version,
        original_filename="synthetic.docx",
        checksum_sha256=(version[-1].encode().hex()[0] * 64),
        byte_size=128,
        uploader=actor,
        approval_reference=f"APPROVAL-{version}",
    )
    template.validation_report = {
        "schema_version": 1,
        "result": "valid" if valid else "invalid",
        "categories": [] if valid else ["not_zip"],
        "counts": {"synthetic_renders": 2} if valid else {"not_zip": 1},
    }
    template.save(update_fields=("validation_report",))
    template.transition_to(
        TemplateVersion.Status.VALID if valid else TemplateVersion.Status.INVALID
    )
    return template


def test_activation_selects_only_the_new_version_for_future_use(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    first = _version(actor, "v1")
    second = _version(actor, "v2")
    original = (first.pk, first.storage_key, first.checksum_sha256, first.byte_size)

    activate_template_version(
        actor=actor,
        template_id=first.pk,
        expected_status=TemplateVersion.Status.VALID,
        expected_active_id=None,
        correlation_id="activate-first",
    )
    result = activate_template_version(
        actor=actor,
        template_id=second.pk,
        expected_status=TemplateVersion.Status.VALID,
        expected_active_id=first.pk,
        correlation_id="activate-second",
    )

    first.refresh_from_db()
    assert result.status == TemplateVersion.Status.ACTIVE
    assert first.status == TemplateVersion.Status.INACTIVE
    active = get_active_template("synthetic-platform-test")
    assert active is not None and active.pk == second.pk
    assert (first.pk, first.storage_key, first.checksum_sha256, first.byte_size) == original


@pytest.mark.parametrize("invalid_kind", ["state", "approval"])
def test_activation_rejects_invalid_candidates(
    user_factory: object, invalid_kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = _actor(user_factory)
    template = _version(actor, "v3", valid=invalid_kind != "state")
    if invalid_kind == "approval":
        template.approval_reference = " "
        monkeypatch.setattr(
            "apps.documents.services._locked_transition_state",
            lambda _template_id: (template, None),
        )

    with pytest.raises(TemplateTransitionConflict):
        activate_template_version(
            actor=actor,
            template_id=template.pk,
            expected_status=template.status,
            expected_active_id=None,
            correlation_id=f"activate-invalid-{invalid_kind}",
        )


def test_repeated_and_stale_transitions_are_recoverable_conflicts(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    template = _version(actor, "v4")
    activate_template_version(
        actor=actor,
        template_id=template.pk,
        expected_status=TemplateVersion.Status.VALID,
        expected_active_id=None,
        correlation_id="activate-once",
    )

    with pytest.raises(TemplateTransitionConflict):
        activate_template_version(
            actor=actor,
            template_id=template.pk,
            expected_status=TemplateVersion.Status.VALID,
            expected_active_id=template.pk,
            correlation_id="activate-repeat",
        )
    deactivate_template_version(
        actor=actor,
        template_id=template.pk,
        expected_status=TemplateVersion.Status.ACTIVE,
        expected_active_id=template.pk,
        correlation_id="deactivate-once",
    )
    with pytest.raises(TemplateTransitionConflict):
        deactivate_template_version(
            actor=actor,
            template_id=template.pk,
            expected_status=TemplateVersion.Status.ACTIVE,
            expected_active_id=None,
            correlation_id="deactivate-repeat",
        )
    assert get_active_template("synthetic-platform-test") is None
    assert (
        AuditEvent.objects.filter(
            action=AuditAction.TEMPLATE_ACTIVATED, outcome=AuditOutcome.FAILURE
        ).count()
        == 1
    )
    assert (
        AuditEvent.objects.filter(
            action=AuditAction.TEMPLATE_DEACTIVATED, outcome=AuditOutcome.FAILURE
        ).count()
        == 1
    )


def test_deactivated_version_cannot_be_reactivated(user_factory: object) -> None:
    actor = _actor(user_factory)
    template = _version(actor, "v4-inactive")
    activate_template_version(
        actor=actor,
        template_id=template.pk,
        expected_status=TemplateVersion.Status.VALID,
        expected_active_id=None,
        correlation_id="activate-before-inactive",
    )
    deactivate_template_version(
        actor=actor,
        template_id=template.pk,
        expected_status=TemplateVersion.Status.ACTIVE,
        expected_active_id=template.pk,
        correlation_id="deactivate-before-reactivation",
    )

    with pytest.raises(TemplateTransitionConflict):
        activate_template_version(
            actor=actor,
            template_id=template.pk,
            expected_status=TemplateVersion.Status.INACTIVE,
            expected_active_id=None,
            correlation_id="reactivation-rejected",
        )


def test_replacement_records_deactivation_and_activation(user_factory: object) -> None:
    actor = _actor(user_factory)
    first = _version(actor, "v4-old")
    second = _version(actor, "v4-new")
    activate_template_version(
        actor=actor,
        template_id=first.pk,
        expected_status=TemplateVersion.Status.VALID,
        expected_active_id=None,
        correlation_id="initial-activation",
    )

    activate_template_version(
        actor=actor,
        template_id=second.pk,
        expected_status=TemplateVersion.Status.VALID,
        expected_active_id=first.pk,
        correlation_id="replacement-activation",
    )

    replacement_event = AuditEvent.objects.get(
        action=AuditAction.TEMPLATE_DEACTIVATED,
        target_id=str(first.pk),
    )
    assert replacement_event.outcome == AuditOutcome.SUCCESS
    assert replacement_event.metadata["reason_code"] == "replaced"


def test_transition_never_changes_historical_bytes_or_identity(user_factory: object) -> None:
    actor = _actor(user_factory)
    template = _version(actor, "v4-bytes")
    storage = storages["private"]
    historical_bytes = b"synthetic historical template bytes"
    storage.save(template.storage_key, ContentFile(historical_bytes))
    identity = (
        template.pk,
        template.type_key,
        template.version,
        template.storage_key,
        template.checksum_sha256,
    )

    activate_template_version(
        actor=actor,
        template_id=template.pk,
        expected_status=TemplateVersion.Status.VALID,
        expected_active_id=None,
        correlation_id="historical-activate",
    )
    deactivate_template_version(
        actor=actor,
        template_id=template.pk,
        expected_status=TemplateVersion.Status.ACTIVE,
        expected_active_id=template.pk,
        correlation_id="historical-deactivate",
    )

    template.refresh_from_db()
    assert (
        template.pk,
        template.type_key,
        template.version,
        template.storage_key,
        template.checksum_sha256,
    ) == identity
    with storage.open(template.storage_key, "rb") as stored:
        assert stored.read() == historical_bytes


def test_activation_and_deactivation_require_distinct_service_permissions(
    user_factory: object,
) -> None:
    owner = _actor(user_factory)
    template = _version(owner, "v5")
    activate_only = _actor(user_factory, "activate-only")
    administrator_group = activate_only.groups.get(name="Administrator")
    administrator_group.permissions.remove(Permission.objects.get(codename="deactivate_templates"))

    activate_template_version(
        actor=activate_only,
        template_id=template.pk,
        expected_status=TemplateVersion.Status.VALID,
        expected_active_id=None,
        correlation_id="activate-permission",
    )
    with pytest.raises(PermissionDenied):
        deactivate_template_version(
            actor=activate_only,
            template_id=template.pk,
            expected_status=TemplateVersion.Status.ACTIVE,
            expected_active_id=template.pk,
            correlation_id="deactivate-denied",
        )


def test_deactivation_does_not_require_activation_permission(user_factory: object) -> None:
    actor = _actor(user_factory)
    active = _version(actor, "v5-active")
    candidate = _version(actor, "v5-candidate")
    activate_template_version(
        actor=actor,
        template_id=active.pk,
        expected_status=TemplateVersion.Status.VALID,
        expected_active_id=None,
        correlation_id="prepare-deactivate-only",
    )
    group = actor.groups.get(name="Administrator")
    group.permissions.remove(Permission.objects.get(codename="activate_templates"))
    actor = User.objects.get(pk=actor.pk)

    deactivate_template_version(
        actor=actor,
        template_id=active.pk,
        expected_status=TemplateVersion.Status.ACTIVE,
        expected_active_id=active.pk,
        correlation_id="deactivate-only",
    )
    with pytest.raises(PermissionDenied):
        activate_template_version(
            actor=actor,
            template_id=candidate.pk,
            expected_status=TemplateVersion.Status.VALID,
            expected_active_id=None,
            correlation_id="activate-denied",
        )


def test_transition_audit_is_safe_and_contains_approval_identity(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    template = _version(actor, "v6")

    activate_template_version(
        actor=actor,
        template_id=template.pk,
        expected_status=TemplateVersion.Status.VALID,
        expected_active_id=None,
        correlation_id="activate-audit",
    )

    event = AuditEvent.objects.get(action=AuditAction.TEMPLATE_ACTIVATED)
    assert event.outcome == AuditOutcome.SUCCESS
    assert event.actor == actor
    assert event.target_id == str(template.pk)
    assert event.metadata == {
        "approval_reference_id": "a5baad83eeb517bc",
        "type_key": "synthetic-platform-test",
        "version": "v6",
    }
    serialized = str(event.metadata)
    assert template.storage_key not in serialized
    assert "checksum" not in serialized and "content" not in serialized


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_racing_activations_leave_exactly_one_active_and_one_conflict(
    user_factory: Callable[..., User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL concurrency profile.")
    actor = _actor(user_factory)
    first = _version(actor, "race-a")
    second = _version(actor, "race-b")
    barrier = Barrier(2)
    from apps.documents import services

    acquire_lock = services._acquire_type_transition_lock

    def synchronize_lock_attempt(type_key: str) -> None:
        barrier.wait()
        acquire_lock(type_key)

    monkeypatch.setattr(services, "_acquire_type_transition_lock", synchronize_lock_attempt)

    def submit(template_id: UUID, suffix: str) -> str:
        close_old_connections()
        thread_actor = User.objects.get(pk=actor.pk)
        try:
            try:
                activate_template_version(
                    actor=thread_actor,
                    template_id=template_id,
                    expected_status=TemplateVersion.Status.VALID,
                    expected_active_id=None,
                    correlation_id=f"activate-race-{suffix}",
                )
            except TemplateTransitionConflict:
                return "conflict"
            return "success"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(lambda args: submit(*args), ((first.pk, "a"), (second.pk, "b")))
        )

    assert sorted(outcomes) == ["conflict", "success"]
    assert (
        TemplateVersion.objects.filter(
            type_key="synthetic-platform-test", status=TemplateVersion.Status.ACTIVE
        ).count()
        == 1
    )
