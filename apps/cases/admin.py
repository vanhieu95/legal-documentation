from __future__ import annotations

from django.contrib import admin

from apps.cases.models import (
    CaseOfficialAssignment,
    CaseParticipant,
    CaseRecord,
    Court,
    Entity,
    EntityAddress,
    Hearing,
    Official,
    Representation,
)


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("code", "full_name", "level", "is_active")
    list_filter = ("level", "is_active")
    search_fields = ("code", "full_name", "short_name")
    autocomplete_fields = ("superior_court",)
    ordering = ("full_name",)


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("legal_name", "kind", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("legal_name", "display_name")
    ordering = ("legal_name",)


@admin.register(EntityAddress)
class EntityAddressAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "entity", "kind", "valid_from", "valid_to", "is_active")
    list_filter = ("kind", "is_active")
    autocomplete_fields = ("entity",)
    readonly_fields = ("full_address", "province", "district", "ward")
    ordering = ("-valid_from",)


@admin.register(Official)
class OfficialAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("entity", "home_court", "title", "position", "is_active")
    list_filter = ("is_active", "home_court")
    search_fields = ("entity__legal_name", "title", "position")
    autocomplete_fields = ("entity", "home_court")
    ordering = ("entity__legal_name",)


@admin.register(CaseRecord)
class CaseRecordAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "status", "procedural_stage", "revision", "updated_at")
    list_filter = ("status", "procedural_stage", "court")
    readonly_fields = (
        "id",
        "created_by",
        "last_edited_by",
        "created_at",
        "updated_at",
        "revision",
        "archived_by",
        "archived_at",
        "archive_reason",
    )
    autocomplete_fields = ("court",)
    ordering = ("-updated_at",)


@admin.register(CaseParticipant)
class CaseParticipantAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "role", "ordering", "is_active")
    list_filter = ("role", "is_active")
    readonly_fields = ("id", "case", "entity")


@admin.register(Representation)
class RepresentationAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "representation_type", "is_active")
    list_filter = ("representation_type", "is_active")
    readonly_fields = ("id", "case", "representative_entity", "represented_participant")


@admin.register(CaseOfficialAssignment)
class CaseOfficialAssignmentAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "role", "ordering", "is_active")
    list_filter = ("role", "is_active")
    readonly_fields = ("id", "case", "official")


@admin.register(Hearing)
class HearingAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "instance_level", "status", "scheduled_at")
    list_filter = ("instance_level", "status")
    readonly_fields = ("id", "case", "created_at", "updated_at")
