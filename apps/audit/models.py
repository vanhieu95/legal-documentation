from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.audit.actions import AuditAction, AuditOutcome


class ImmutableAuditEventError(Exception):
    """Raised when a caller attempts to mutate an audit event."""


class AuditEventQuerySet(models.QuerySet["AuditEvent"]):
    """Prevent bulk mutation of append-only audit rows."""

    def update(self, **kwargs: Any) -> int:
        raise ImmutableAuditEventError("Audit events are append-only and cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableAuditEventError("Audit events are append-only and cannot be deleted.")


class AuditEventManager(models.Manager["AuditEvent"]):
    """Expose append-only queryset behavior."""

    def get_queryset(self) -> AuditEventQuerySet:
        return AuditEventQuerySet(self.model, using=self._db)


class AuditEvent(models.Model):
    """Append-only audit record with bounded metadata and generic target references."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_events",
        editable=False,
    )
    is_system_actor = models.BooleanField(default=False, editable=False)
    action = models.CharField(max_length=64, editable=False, db_index=True)
    target_type = models.CharField(max_length=64, editable=False, db_index=True)
    target_id = models.CharField(max_length=128, blank=True, default="", editable=False)
    outcome = models.CharField(max_length=32, editable=False, db_index=True)
    correlation_id = models.CharField(max_length=128, editable=False, db_index=True)
    changed_fields = models.JSONField(default=list, editable=False)
    metadata = models.JSONField(default=dict, editable=False)

    objects = AuditEventManager()

    class Meta:
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["actor", "occurred_at"]),
            models.Index(fields=["outcome", "occurred_at"]),
            models.Index(fields=["correlation_id", "occurred_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(is_system_actor=True, actor__isnull=True)
                    | models.Q(is_system_actor=False, actor__isnull=False)
                ),
                name="audit_event_actor_marker_consistency",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action}:{self.outcome}@{self.occurred_at.isoformat()}"

    def clean(self) -> None:
        super().clean()
        if self.action not in AuditAction:
            raise ValidationError({"action": "Unsupported audit action."})
        if self.outcome not in AuditOutcome:
            raise ValidationError({"outcome": "Unsupported audit outcome."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableAuditEventError("Audit events are append-only and cannot be updated.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableAuditEventError("Audit events are append-only and cannot be deleted.")
