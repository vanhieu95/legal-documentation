from __future__ import annotations

from django.contrib import admin

from apps.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Operational read-only access to append-only audit events."""

    list_display = (
        "occurred_at",
        "action",
        "outcome",
        "actor",
        "is_system_actor",
        "target_type",
        "target_id",
        "correlation_id",
    )
    list_filter = ("action", "outcome", "target_type", "is_system_actor")
    search_fields = ("correlation_id", "target_id", "action")
    ordering = ("-occurred_at",)
    readonly_fields = (
        "id",
        "occurred_at",
        "actor",
        "is_system_actor",
        "action",
        "target_type",
        "target_id",
        "outcome",
        "correlation_id",
        "changed_fields",
        "metadata",
    )

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: AuditEvent | None = None) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: AuditEvent | None = None) -> bool:
        return False
