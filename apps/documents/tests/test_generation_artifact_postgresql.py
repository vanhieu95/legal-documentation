from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from uuid import UUID

import pytest
from django.contrib.auth.models import User
from django.core.files.base import File
from django.db import close_old_connections, connection

from apps.audit.actions import AuditAction
from apps.audit.models import AuditEvent
from apps.core.storage import PrivateFileSystemStorage
from apps.documents.generation_artifacts import generate_artifact
from apps.documents.models import GeneratedDocument
from apps.documents.tests.test_generation_artifacts import _artifact_names, _prepared_attempt

pytestmark = [pytest.mark.postgresql, pytest.mark.django_db(transaction=True)]


def _require_postgresql() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL artifact finalization races.")


def _generate(
    *,
    barrier: Barrier,
    actor_id: int,
    attempt_id: UUID,
    storage: PrivateFileSystemStorage,
    correlation_id: str,
) -> tuple[str, str]:
    close_old_connections()
    try:
        barrier.wait()
        attempt = generate_artifact(
            actor=User.objects.get(pk=actor_id),
            attempt_id=attempt_id,
            correlation_id=correlation_id,
            storage=storage,
        )
        return attempt.status, attempt.output_storage_key
    finally:
        close_old_connections()


def test_concurrent_finalizers_publish_one_artifact_and_one_success_audit(
    user_factory: object,
    tmp_path: Path,
) -> None:
    _require_postgresql()
    actor, _draft, attempt, storage, _package = _prepared_attempt(user_factory, tmp_path)
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda index: _generate(
                    barrier=barrier,
                    actor_id=actor.pk,
                    attempt_id=attempt.pk,
                    storage=PrivateFileSystemStorage(location=tmp_path),
                    correlation_id=f"postgresql-artifact-race-{index}",
                ),
                range(2),
            )
        )

    assert [status for status, _key in results] == [
        GeneratedDocument.Status.GENERATED,
        GeneratedDocument.Status.GENERATED,
    ]
    assert results[0][1] == results[1][1]
    assert _artifact_names(storage) == [results[0][1]]
    assert (
        AuditEvent.objects.filter(
            action=AuditAction.DOCUMENT_GENERATION_SUCCEEDED,
            target_id=str(attempt.pk),
        ).count()
        == 1
    )


class _FailAfterWinnerStorage(PrivateFileSystemStorage):
    def __init__(self, *, location: Path, reached: Event, winner_done: Event) -> None:
        super().__init__(location=location)
        self.reached = reached
        self.winner_done = winner_done

    def save_immutable(self, name: str, content: File[bytes]) -> str:
        if name.startswith("generated/"):
            self.reached.set()
            assert self.winner_done.wait(timeout=10)
            super().save_immutable(name, content)
            raise OSError("synthetic storage failure")
        return super().save_immutable(name, content)


def test_concurrent_storage_failure_cannot_rewrite_a_successful_attempt(
    user_factory: object,
    tmp_path: Path,
) -> None:
    _require_postgresql()
    actor, _draft, attempt, storage, _package = _prepared_attempt(user_factory, tmp_path)
    failure_reached = Event()
    winner_done = Event()
    failing_storage = _FailAfterWinnerStorage(
        location=tmp_path,
        reached=failure_reached,
        winner_done=winner_done,
    )

    def fail() -> tuple[str, str]:
        return _generate(
            barrier=Barrier(1),
            actor_id=actor.pk,
            attempt_id=attempt.pk,
            storage=failing_storage,
            correlation_id="postgresql-artifact-failure-race",
        )

    def succeed() -> tuple[str, str]:
        assert failure_reached.wait(timeout=10)
        try:
            return _generate(
                barrier=Barrier(1),
                actor_id=actor.pk,
                attempt_id=attempt.pk,
                storage=PrivateFileSystemStorage(location=tmp_path),
                correlation_id="postgresql-artifact-success-race",
            )
        finally:
            winner_done.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        failed_future = pool.submit(fail)
        successful_future = pool.submit(succeed)
        successful = successful_future.result(timeout=20)
        raced_failure = failed_future.result(timeout=20)

    assert successful == raced_failure
    assert successful[0] == GeneratedDocument.Status.GENERATED
    assert _artifact_names(storage) == [successful[1]]
    attempt.refresh_from_db()
    assert attempt.status == GeneratedDocument.Status.GENERATED
    assert not AuditEvent.objects.filter(
        action=AuditAction.DOCUMENT_GENERATION_FAILED,
        target_id=str(attempt.pk),
    ).exists()
