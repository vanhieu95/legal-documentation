from __future__ import annotations

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.test import Client
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch

from apps.accounts.permissions import seed_administrator_permissions
from apps.audit.models import AuditEvent
from apps.cases.forms import CaseArchiveForm, CaseRestoreForm
from apps.cases.models import CaseRecord
from apps.cases.policies import can_edit_case, can_generate_documents_for_case
from apps.cases.services import CaseRevisionConflict, archive_case, restore_case


@pytest.fixture
def administrator_group() -> Group:
    return seed_administrator_permissions()


@pytest.fixture
def administrator(user_factory: Callable[..., User], administrator_group: Group) -> User:
    user = user_factory(username="synthetic-case-archive-admin")
    user.groups.add(administrator_group)
    return user


def archive_form(case: CaseRecord, *, reason: str = "Synthetic archive reason") -> CaseArchiveForm:
    return CaseArchiveForm(data={"expected_revision": case.revision, "reason": reason})


def restore_form(case: CaseRecord) -> CaseRestoreForm:
    return CaseRestoreForm(data={"expected_revision": case.revision})


def transition_url(case: CaseRecord | uuid.UUID, operation: str) -> str:
    object_id = case.pk if isinstance(case, CaseRecord) else case
    return reverse(f"cases:{operation}", kwargs={"case_id": object_id})


@pytest.mark.django_db
def test_archive_service_sets_server_metadata_and_increments_once(
    administrator: User, case_factory: Callable[..., CaseRecord]
) -> None:
    case = case_factory()
    form = archive_form(case, reason="  Lý do lưu trữ Unicode  ")
    assert form.is_valid()

    archived = archive_case(
        actor=administrator,
        case_id=case.pk,
        form=form,
        correlation_id="case-archive-success",
    )

    assert archived.status == CaseRecord.Status.ARCHIVED
    assert archived.revision == 2
    assert archived.archived_by == administrator
    assert archived.archived_at is not None
    assert archived.archive_reason == "Lý do lưu trữ Unicode"
    assert not can_edit_case(archived)
    assert not can_generate_documents_for_case(archived)
    event = AuditEvent.objects.get(action="case.archived")
    assert event.changed_fields == ["archive_reason", "archived_at", "archived_by", "status"]
    assert event.metadata == {"reason_supplied": True}
    assert "Unicode" not in str(event.metadata)


@pytest.mark.django_db
def test_restore_service_clears_current_archive_metadata_and_increments_once(
    administrator: User, case_factory: Callable[..., CaseRecord]
) -> None:
    case = archive_case(
        actor=administrator,
        case_id=case_factory().pk,
        form=CaseArchiveForm(data={"expected_revision": 1, "reason": "Synthetic archive"}),
        correlation_id="case-archive-before-restore",
    )

    restored = restore_case(
        actor=administrator,
        case_id=case.pk,
        form=restore_form(case),
        correlation_id="case-restore-success",
    )

    assert restored.status == CaseRecord.Status.ACTIVE
    assert restored.revision == 3
    assert restored.archived_by is None
    assert restored.archived_at is None
    assert restored.archive_reason == ""
    assert can_edit_case(restored)
    assert can_generate_documents_for_case(restored)
    assert AuditEvent.objects.filter(action="case.archived", outcome="success").count() == 1
    event = AuditEvent.objects.get(action="case.restored")
    assert event.changed_fields == ["archive_reason", "archived_at", "archived_by", "status"]
    assert event.metadata == {}


@pytest.mark.django_db
def test_archive_reason_is_required_bounded_and_preserves_vietnamese_unicode(
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    blank = archive_form(case, reason="   ")
    excessive = archive_form(case, reason="x" * 501)
    valid = archive_form(case, reason="Đương sự đề nghị lưu hồ sơ")

    assert not blank.is_valid()
    assert not excessive.is_valid()
    assert valid.is_valid()
    assert valid.cleaned_data["reason"] == "Đương sự đề nghị lưu hồ sơ"


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["archive", "restore"])
def test_repeated_transition_is_a_conflict_without_an_extra_revision(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    operation: str,
) -> None:
    case = case_factory()
    if operation == "archive":
        case = archive_case(
            actor=administrator,
            case_id=case.pk,
            form=archive_form(case),
            correlation_id="case-repeat-setup",
        )
        expected_action = "case.archived"
        with pytest.raises(CaseRevisionConflict):
            archive_case(
                actor=administrator,
                case_id=case.pk,
                form=archive_form(case),
                correlation_id="case-repeat-conflict",
            )
    else:
        case = archive_case(
            actor=administrator,
            case_id=case.pk,
            form=archive_form(case),
            correlation_id="case-repeat-archive-setup",
        )
        case = restore_case(
            actor=administrator,
            case_id=case.pk,
            form=restore_form(case),
            correlation_id="case-repeat-restore-setup",
        )
        expected_action = "case.restored"
        with pytest.raises(CaseRevisionConflict):
            restore_case(
                actor=administrator,
                case_id=case.pk,
                form=restore_form(case),
                correlation_id="case-repeat-conflict",
            )

    case.refresh_from_db()
    assert case.revision == (2 if operation == "archive" else 3)
    failure = AuditEvent.objects.get(
        action=expected_action,
        outcome="failure",
        correlation_id="case-repeat-conflict",
    )
    assert failure.metadata["reason_code"] == "state_conflict"
    if operation == "archive":
        assert failure.metadata["reason_supplied"] is True


@pytest.mark.django_db
def test_stale_archive_and_restore_never_overwrite_a_newer_revision(
    administrator: User, case_factory: Callable[..., CaseRecord]
) -> None:
    active = case_factory()
    stale_archive = archive_form(active)
    CaseRecord.objects.filter(pk=active.pk).update(revision=2)

    with pytest.raises(CaseRevisionConflict):
        archive_case(
            actor=administrator,
            case_id=active.pk,
            form=stale_archive,
            correlation_id="case-stale-archive",
        )

    archived = case_factory()
    archived = archive_case(
        actor=administrator,
        case_id=archived.pk,
        form=archive_form(archived),
        correlation_id="case-stale-restore-setup",
    )
    stale_restore = restore_form(archived)
    CaseRecord.objects.filter(pk=archived.pk).update(revision=3)

    with pytest.raises(CaseRevisionConflict):
        restore_case(
            actor=administrator,
            case_id=archived.pk,
            form=stale_restore,
            correlation_id="case-stale-restore",
        )

    assert AuditEvent.objects.get(correlation_id="case-stale-archive").metadata == {
        "reason_code": "revision_conflict",
        "reason_supplied": True,
    }
    assert AuditEvent.objects.get(correlation_id="case-stale-restore").metadata == {
        "reason_code": "revision_conflict"
    }


@pytest.mark.django_db
def test_archive_and_restore_services_require_their_separate_permissions(
    user_factory: Callable[..., User], case_factory: Callable[..., CaseRecord]
) -> None:
    outsider = user_factory(username="synthetic-transition-outsider")
    case = case_factory()

    with pytest.raises(PermissionDenied):
        archive_case(
            actor=outsider,
            case_id=case.pk,
            form=archive_form(case),
            correlation_id="case-archive-denied",
        )
    with pytest.raises(PermissionDenied):
        restore_case(
            actor=outsider,
            case_id=case.pk,
            form=CaseRestoreForm(data={"expected_revision": 1}),
            correlation_id="case-restore-denied",
        )

    assert set(
        AuditEvent.objects.filter(action="identity.access_denied").values_list(
            "metadata__permission", flat=True
        )
    ) == {"accounts.archive_cases", "accounts.restore_cases"}


@pytest.mark.django_db
def test_full_and_htmx_archive_confirmations_are_safe_and_revision_aware(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory(internal_reference="SYN-CONFIRM-ARCHIVE")
    client.force_login(administrator)

    full = client.get(transition_url(case, "archive"))
    htmx = client.get(transition_url(case, "archive"), HTTP_HX_REQUEST="true")

    assert full.status_code == 200
    assert "<html" in full.content.decode()
    assert "SYN-CONFIRM-ARCHIVE" in full.content.decode()
    assert 'name="expected_revision" value="1"' in full.content.decode()
    assert htmx.status_code == 200
    assert "<html" not in htmx.content.decode()
    assert 'id="case-transition-form"' in htmx.content.decode()
    assert "HX-Request" in htmx.headers["Vary"]
    case.refresh_from_db()
    assert case.status == CaseRecord.Status.ACTIVE


@pytest.mark.django_db
def test_archive_and_restore_post_support_full_and_htmx_results(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    client.force_login(administrator)

    archived = client.post(
        transition_url(case, "archive"),
        {"expected_revision": 1, "reason": "Synthetic HTTP archive"},
    )
    case.refresh_from_db()
    restored = client.post(
        transition_url(case, "restore"),
        {"expected_revision": 2},
        HTTP_HX_REQUEST="true",
    )

    assert archived.status_code == 302
    assert archived.headers["Location"] == reverse("cases:detail", kwargs={"case_id": case.pk})
    assert restored.status_code == 204
    assert restored.headers["HX-Redirect"] == reverse("cases:detail", kwargs={"case_id": case.pk})
    case.refresh_from_db()
    assert case.status == CaseRecord.Status.ACTIVE
    assert case.revision == 3


@pytest.mark.django_db
def test_archive_validation_and_conflict_return_accessible_responses_and_safe_audits(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    client.force_login(administrator)

    invalid = client.post(
        transition_url(case, "archive"),
        {"expected_revision": 1, "reason": "   "},
        HTTP_HX_REQUEST="true",
    )
    CaseRecord.objects.filter(pk=case.pk).update(revision=2)
    conflict = client.post(
        transition_url(case, "archive"),
        {"expected_revision": 1, "reason": "Sensitive conflict reason"},
    )

    assert invalid.status_code == 422
    assert "data-error-summary" in invalid.content.decode()
    assert conflict.status_code == 409
    assert "data-conflict-summary" in conflict.content.decode()
    validation_event = AuditEvent.objects.get(
        action="case.archived", metadata__reason_code="validation_error"
    )
    conflict_event = AuditEvent.objects.get(
        action="case.archived", metadata__reason_code="revision_conflict"
    )
    assert validation_event.target_id == str(case.pk)
    assert conflict_event.target_id == str(case.pk)
    assert validation_event.metadata["reason_supplied"] is False
    assert conflict_event.metadata["reason_supplied"] is True
    assert "Sensitive" not in str(conflict_event.metadata)


@pytest.mark.django_db
def test_archived_case_remains_viewable_but_edit_is_forbidden_then_restored_edit_is_available(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    case = archive_case(
        actor=administrator,
        case_id=case.pk,
        form=archive_form(case),
        correlation_id="case-view-archived-setup",
    )
    client.force_login(administrator)

    detail = client.get(reverse("cases:detail", kwargs={"case_id": case.pk}))
    edit_denied = client.get(reverse("cases:edit", kwargs={"case_id": case.pk}))
    client.post(transition_url(case, "restore"), {"expected_revision": case.revision})
    edit_restored = client.get(reverse("cases:edit", kwargs={"case_id": case.pk}))

    assert detail.status_code == 200
    assert "data-case-dialog-trigger" in detail.content.decode()
    assert edit_denied.status_code == 403
    assert edit_restored.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["archive", "restore"])
@pytest.mark.parametrize("is_htmx", [False, True])
def test_case_transition_rejects_missing_csrf(
    csrf_client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    operation: str,
    is_htmx: bool,
) -> None:
    case = case_factory()
    if operation == "restore":
        case = archive_case(
            actor=administrator,
            case_id=case.pk,
            form=archive_form(case),
            correlation_id="case-csrf-restore-setup",
        )
    csrf_client.force_login(administrator)
    payload = (
        {"expected_revision": case.revision, "reason": "Synthetic CSRF archive"}
        if operation == "archive"
        else {"expected_revision": case.revision}
    )

    response = csrf_client.post(
        transition_url(case, operation),
        payload,
        headers={"HX-Request": "true"} if is_htmx else None,
    )

    assert response.status_code == 403
    case.refresh_from_db()
    assert case.revision == (2 if operation == "restore" else 1)


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["archive", "restore"])
@pytest.mark.parametrize(
    ("principal", "permission_codename", "expected"),
    [
        ("anonymous", None, 302),
        ("inactive", None, 302),
        ("outsider", None, 403),
        ("administrator", "archive_cases", 403),
        ("administrator", "restore_cases", 403),
        ("administrator", None, 200),
        ("superuser", None, 200),
    ],
)
def test_case_transition_authorization_matrix(
    client: Client,
    user_factory: Callable[..., User],
    administrator_group: Group,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    operation: str,
    principal: str,
    permission_codename: str | None,
    expected: int,
) -> None:
    case = case_factory()
    if operation == "restore":
        case.status = CaseRecord.Status.ARCHIVED
        case.archived_by = case.created_by
        case.archived_at = case.updated_at
        case.archive_reason = "Synthetic archived state"
        case.save()
    if principal == "anonymous":
        user = None
    elif principal == "inactive":
        user = user_factory(username=f"synthetic-{operation}-inactive", is_active=False)
    elif principal == "outsider":
        user = user_factory(username=f"synthetic-{operation}-outsider")
    elif principal == "superuser":
        user = user_factory(
            username=f"synthetic-{operation}-superuser", is_superuser=True, is_staff=True
        )
    else:
        user = administrator
    relevant_permission = f"{operation}_cases"
    if permission_codename == relevant_permission:
        administrator_group.permissions.remove(Permission.objects.get(codename=permission_codename))
    if user:
        client.force_login(user)

    if principal == "administrator" and permission_codename not in {None, relevant_permission}:
        expected = 200
    assert client.get(transition_url(case, operation)).status_code == expected


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["archive", "restore"])
def test_transition_uses_generic_not_found_for_inaccessible_uuid(
    client: Client, administrator: User, operation: str
) -> None:
    guessed = uuid.uuid4()
    client.force_login(administrator)

    response = client.get(transition_url(guessed, operation))

    assert response.status_code == 404
    assert str(guessed) not in response.content.decode()


def test_no_hard_delete_case_route_or_supported_service_exists() -> None:
    from apps.cases import services

    with pytest.raises(NoReverseMatch):
        reverse("cases:delete", kwargs={"case_id": uuid.uuid4()})
    assert not hasattr(services, "delete_case")


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["archive", "restore"])
def test_postgresql_concurrent_transition_allows_exactly_one_change(
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    operation: str,
) -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run the explicit PostgreSQL concurrency profile.")
    case = case_factory()
    if operation == "restore":
        case = archive_case(
            actor=administrator,
            case_id=case.pk,
            form=archive_form(case),
            correlation_id="case-concurrent-restore-setup",
        )
    expected_revision = case.revision
    barrier = Barrier(2)

    def submit(suffix: str) -> str:
        close_old_connections()
        actor = User.objects.get(pk=administrator.pk)
        barrier.wait()
        try:
            if operation == "archive":
                archive = CaseArchiveForm(
                    data={
                        "expected_revision": expected_revision,
                        "reason": f"Synthetic {suffix}",
                    }
                )
                assert archive.is_valid()
                archive_case(
                    actor=actor,
                    case_id=case.pk,
                    form=archive,
                    correlation_id=f"case-concurrent-archive-{suffix}",
                )
            else:
                restore = CaseRestoreForm(data={"expected_revision": expected_revision})
                assert restore.is_valid()
                restore_case(
                    actor=actor,
                    case_id=case.pk,
                    form=restore,
                    correlation_id=f"case-concurrent-restore-{suffix}",
                )
        except CaseRevisionConflict:
            return "conflict"
        finally:
            close_old_connections()
        return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, ("A", "B")))

    assert sorted(outcomes) == ["conflict", "success"]
    case.refresh_from_db()
    expected_status = (
        CaseRecord.Status.ARCHIVED if operation == "archive" else CaseRecord.Status.ACTIVE
    )
    assert case.status == expected_status
    assert case.revision == expected_revision + 1
