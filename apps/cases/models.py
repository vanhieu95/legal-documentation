from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
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


class CaseRecord(models.Model):
    class ProceduralStage(models.TextChoices):
        PRE_ACCEPTANCE = "pre_acceptance", _("Pre-acceptance")
        ACCEPTED = "accepted", _("Accepted")
        PREPARATION = "preparation", _("Preparation")
        HEARING = "hearing", _("Hearing")
        RESOLVED = "resolved", _("Resolved")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        ARCHIVED = "archived", _("Archived")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    internal_reference = models.CharField(max_length=64, unique=True)
    court = models.ForeignKey(Court, on_delete=models.PROTECT, related_name="cases")
    matter_type = models.CharField(max_length=255)
    procedural_stage = models.CharField(max_length=24, choices=ProceduralStage.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    acceptance_number = models.CharField(max_length=64, blank=True)
    acceptance_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(9999)],
    )
    acceptance_date = models.DateField(null=True, blank=True)
    acceptance_type_code = models.CharField(max_length=32, blank=True)
    revision = models.PositiveBigIntegerField(default=1, validators=[MinValueValidator(1)])
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_case_records",
        editable=False,
    )
    last_edited_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="edited_case_records",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)
    archived_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="archived_case_records",
        editable=False,
    )
    archived_at = models.DateTimeField(null=True, blank=True, editable=False)
    archive_reason = models.CharField(max_length=500, blank=True, editable=False)

    class Meta:
        ordering = ("-updated_at", "id")
        indexes = [
            models.Index(fields=["status", "procedural_stage"], name="case_record_state_stage_idx"),
            models.Index(fields=["court", "status"], name="case_record_court_state_idx"),
            models.Index(
                fields=["acceptance_year", "acceptance_type_code", "acceptance_date"],
                name="case_record_acceptance_idx",
            ),
            models.Index(fields=["updated_at"], name="case_record_updated_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        procedural_stage="pre_acceptance",
                        acceptance_number="",
                        acceptance_year__isnull=True,
                        acceptance_date__isnull=True,
                        acceptance_type_code="",
                    )
                    | (
                        ~Q(procedural_stage="pre_acceptance")
                        & Q(acceptance_number__gt="")
                        & Q(acceptance_year__isnull=False)
                        & Q(acceptance_date__isnull=False)
                        & Q(acceptance_type_code__gt="")
                    )
                ),
                name="case_record_acceptance_group_valid",
            ),
            models.CheckConstraint(
                condition=Q(revision__gte=1),
                name="case_record_revision_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status="active",
                        archived_by__isnull=True,
                        archived_at__isnull=True,
                        archive_reason="",
                    )
                    | Q(
                        status="archived",
                        archived_by__isnull=False,
                        archived_at__isnull=False,
                        archive_reason__gt="",
                    )
                ),
                name="case_record_archive_metadata_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    procedural_stage__in=(
                        "pre_acceptance",
                        "accepted",
                        "preparation",
                        "hearing",
                        "resolved",
                    )
                ),
                name="case_record_stage_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("active", "archived")),
                name="case_record_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(acceptance_year__isnull=True)
                    | Q(acceptance_year__gte=1900, acceptance_year__lte=9999)
                ),
                name="case_record_acceptance_year_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"Case record {self.pk}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, ValidationError] = {}
        acceptance_fields = {
            "acceptance_number": self.acceptance_number,
            "acceptance_year": self.acceptance_year,
            "acceptance_date": self.acceptance_date,
            "acceptance_type_code": self.acceptance_type_code,
        }
        is_pre_acceptance = self.procedural_stage == self.ProceduralStage.PRE_ACCEPTANCE
        for field_name, value in acceptance_fields.items():
            present = value is not None and value != ""
            if (is_pre_acceptance and present) or (not is_pre_acceptance and not present):
                errors[field_name] = ValidationError(
                    _("Acceptance details must be completed together after acceptance."),
                    code="acceptance_group",
                )

        archive_values = (self.archived_by_id, self.archived_at, self.archive_reason)
        if self.status == self.Status.ACTIVE and any(archive_values):
            errors["status"] = ValidationError(
                _("Active cases cannot contain archive metadata."), code="archive_state"
            )
        if self.status == self.Status.ARCHIVED and not all(archive_values):
            errors["status"] = ValidationError(
                _("Archived cases require complete archive metadata."), code="archive_state"
            )
        if errors:
            raise ValidationError(errors)
