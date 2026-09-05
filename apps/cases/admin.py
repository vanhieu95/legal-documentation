from __future__ import annotations

from django.contrib import admin

from apps.cases.models import Court, Entity, EntityAddress, Official


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
