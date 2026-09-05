from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _


class Court(models.Model):
    class Level(models.TextChoices):
        DISTRICT = "district", _("District-level court")
        PROVINCIAL = "provincial", _("Provincial-level court")
        HIGH = "high", _("High People's Court")
        SUPREME = "supreme", _("Supreme People's Court")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=32, unique=True)
    full_name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=128)
    level = models.CharField(max_length=16, choices=Level.choices)
    address = models.CharField(max_length=500)
    superior_court = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subordinate_courts",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("full_name", "code")
        indexes = [
            models.Index(fields=["is_active", "full_name"], name="case_court_active_name_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(id=F("superior_court_id")),
                name="case_court_superior_not_self",
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.short_name}"

    def clean(self) -> None:
        super().clean()
        if self.superior_court_id is not None and self.superior_court_id == self.pk:
            raise ValidationError({"superior_court": _("A court cannot be its own superior.")})


class Entity(models.Model):
    class Kind(models.TextChoices):
        INDIVIDUAL = "individual", _("Individual")
        ORGANIZATION = "organization", _("Organization")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    legal_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    identity_document_number = models.CharField(max_length=64, blank=True)
    registration_number = models.CharField(max_length=64, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    organization_type = models.CharField(max_length=128, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("legal_name", "id")
        indexes = [
            models.Index(
                fields=["is_active", "kind", "legal_name"], name="case_entity_kind_name_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        kind="individual",
                        identity_document_number__gt="",
                        registration_number="",
                        organization_type="",
                    )
                    | Q(
                        kind="organization",
                        identity_document_number="",
                        registration_number__gt="",
                        date_of_birth__isnull=True,
                    )
                ),
                name="case_entity_kind_fields_valid",
            ),
            models.UniqueConstraint(
                fields=["identity_document_number"],
                condition=~Q(identity_document_number=""),
                name="case_entity_identity_unique",
            ),
            models.UniqueConstraint(
                fields=["registration_number"],
                condition=~Q(registration_number=""),
                name="case_entity_registration_unique",
            ),
        ]

    def __str__(self) -> str:
        return self.display_name or self.legal_name

    def clean(self) -> None:
        super().clean()
        errors: dict[str, ValidationError] = {}
        if self.kind == self.Kind.INDIVIDUAL:
            if not self.identity_document_number:
                errors["identity_document_number"] = ValidationError(
                    _("An identity document number is required for an individual."),
                    code="required_for_kind",
                )
            if self.registration_number:
                errors["registration_number"] = ValidationError(
                    _("A registration number is only valid for an organization."),
                    code="invalid_for_kind",
                )
            if self.organization_type:
                errors["organization_type"] = ValidationError(
                    _("Organization type is only valid for an organization."),
                    code="invalid_for_kind",
                )
        elif self.kind == self.Kind.ORGANIZATION:
            if not self.registration_number:
                errors["registration_number"] = ValidationError(
                    _("A registration number is required for an organization."),
                    code="required_for_kind",
                )
            if self.identity_document_number:
                errors["identity_document_number"] = ValidationError(
                    _("An identity document number is only valid for an individual."),
                    code="invalid_for_kind",
                )
            if self.date_of_birth is not None:
                errors["date_of_birth"] = ValidationError(
                    _("Date of birth is only valid for an individual."),
                    code="invalid_for_kind",
                )
        if errors:
            raise ValidationError(errors)


class EntityAddress(models.Model):
    class Kind(models.TextChoices):
        PERMANENT = "permanent", _("Permanent address")
        CURRENT = "current", _("Current address")
        REGISTERED_OFFICE = "registered_office", _("Registered office")
        CONTACT = "contact", _("Contact address")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="addresses")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    full_address = models.CharField(max_length=500)
    province = models.CharField(max_length=128, blank=True)
    district = models.CharField(max_length=128, blank=True)
    ward = models.CharField(max_length=128, blank=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("entity", "kind", "-valid_from", "id")
        indexes = [
            models.Index(
                fields=["entity", "kind", "valid_to"],
                name="case_address_history_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(valid_from__isnull=True)
                    | Q(valid_to__isnull=True)
                    | Q(valid_to__gte=F("valid_from"))
                ),
                name="case_address_validity_order",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} ({self.entity_id})"

    def clean(self) -> None:
        super().clean()
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError({"valid_to": _("The end date cannot be before the start date.")})


class Official(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.OneToOneField(Entity, on_delete=models.PROTECT, related_name="official")
    home_court = models.ForeignKey(Court, on_delete=models.PROTECT, related_name="officials")
    title = models.CharField(max_length=128)
    position = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("entity__legal_name", "id")
        indexes = [
            models.Index(
                fields=["home_court", "is_active"],
                name="case_official_court_active_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.entity} — {self.title}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, ValidationError] = {}
        if self.entity_id is not None and self.entity.kind != Entity.Kind.INDIVIDUAL:
            errors["entity"] = ValidationError(
                _("An official must reference an individual."), code="invalid_kind"
            )
        if self.is_active and self.entity_id is not None and not self.entity.is_active:
            errors["entity"] = ValidationError(
                _("An active official requires an active individual."), code="inactive"
            )
        if self.is_active and self.home_court_id is not None and not self.home_court.is_active:
            errors["home_court"] = ValidationError(
                _("An active official requires an active home court."), code="inactive"
            )
        if errors:
            raise ValidationError(errors)
