from __future__ import annotations

import json
import math
import re
import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Cast, Concat, Replace
from django.db.models.lookups import StartsWith
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.documents.limits import MAX_TEMPLATE_BYTES
from apps.documents.registry import (
    RESERVED_DRAFT_FIELD_NAMES,
    UnknownDocumentTypeKey,
    document_registry,
)
from apps.documents.storage_keys import (
    MAX_DISPLAY_FILENAME_LENGTH,
    build_template_storage_key,
    sanitize_template_display_filename,
)

MAX_VALIDATION_REPORT_BYTES = 4096
MAX_DRAFT_PAYLOAD_BYTES = 64 * 1024
MAX_GENERATION_INPUT_SNAPSHOT_BYTES = 64 * 1024
MAX_GENERATION_RESOLVED_SNAPSHOT_BYTES = 256 * 1024
MAX_GENERATION_OVERRIDE_SNAPSHOT_BYTES = 64 * 1024
MAX_GENERATION_TEMPLATE_SNAPSHOT_BYTES = 2 * 1024
MAX_VALIDATION_REPORT_ITEMS = 50
MAX_VALIDATION_REPORT_DEPTH = 4
MAX_VALIDATION_REPORT_STRING_LENGTH = 500
_STORAGE_KEY_PATTERN = re.compile(
    r"^templates/(?:vds-[0-9]{2}|synthetic-[a-z0-9]+(?:-[a-z0-9]+)*)/"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}/[0-9a-f]{32}\.docx$"
)
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SAFE_REPORT_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SENSITIVE_REPORT_KEY_PARTS = ("path", "content", "payload", "snapshot", "bytes", "secret")
_GENERATION_TYPE_KEY_PATTERN = r"^(?:vds-[0-9]{2}|synthetic-[a-z0-9]+(?:-[a-z0-9]+)*)$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_SAFE_CORRELATION_PATTERN = r"^(?:|[A-Za-z0-9][A-Za-z0-9._:-]{0,127})$"
_GENERATED_STORAGE_KEY_PATTERN = (
    r"^(?:|generated/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,144}\.docx)$"
)
_GENERATED_FILENAME_PATTERN = r"^(?:|[^/\\\x00-\x1f\x7f]{1,145}\.docx)$"


def validate_document_draft_payload(value: object) -> None:
    if not isinstance(value, dict):
        raise ValidationError(_("A document draft payload must be a JSON object."))
    if any(not isinstance(key, str) or key in RESERVED_DRAFT_FIELD_NAMES for key in value):
        raise ValidationError(_("The document draft payload contains a prohibited field."))
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValidationError(_("A document draft payload must contain JSON values.")) from error
    if len(encoded) > MAX_DRAFT_PAYLOAD_BYTES:
        raise ValidationError(_("The document draft payload exceeds the allowed size."))


def _validate_snapshot_value(
    value: object, *, depth: int = 0, seen: list[int] | None = None
) -> None:
    if seen is None:
        seen = [0]
    seen[0] += 1
    if seen[0] > 5_000:
        raise ValidationError(_("The generation snapshot has too many values."))
    if depth > 8:
        raise ValidationError(_("The generation snapshot is too deeply nested."))
    if isinstance(value, dict):
        if len(value) > 500:
            raise ValidationError(_("The generation snapshot has too many entries."))
        for key, nested in value.items():
            if not isinstance(key, str) or not key or len(key) > 128:
                raise ValidationError(_("The generation snapshot has an invalid field name."))
            _validate_snapshot_value(nested, depth=depth + 1, seen=seen)
        return
    if isinstance(value, list):
        if len(value) > 500:
            raise ValidationError(_("The generation snapshot has too many entries."))
        for nested in value:
            _validate_snapshot_value(nested, depth=depth + 1, seen=seen)
        return
    if isinstance(value, str) and len(value) <= 16_384:
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValidationError(_("The generation snapshot contains an unsupported value."))
    if value is None or isinstance(value, (bool, int, float)):
        return
    raise ValidationError(_("The generation snapshot contains an unsupported value."))


def _validate_snapshot_envelope(value: object, *, maximum: int) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "values"}
        or type(value.get("version")) is not int
        or value["version"] != 1
        or not isinstance(value.get("values"), dict)
    ):
        raise ValidationError(_("The generation snapshot envelope is invalid."))
    _validate_snapshot_value(value)
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValidationError(_("The generation snapshot must contain JSON values.")) from error
    if len(encoded) > maximum:
        raise ValidationError(_("The generation snapshot exceeds the allowed size."))


def validate_generation_input_snapshot(value: object) -> None:
    _validate_snapshot_envelope(value, maximum=MAX_GENERATION_INPUT_SNAPSHOT_BYTES)


def validate_generation_resolved_snapshot(value: object) -> None:
    _validate_snapshot_envelope(value, maximum=MAX_GENERATION_RESOLVED_SNAPSHOT_BYTES)


def validate_generation_override_snapshot(value: object) -> None:
    _validate_snapshot_envelope(value, maximum=MAX_GENERATION_OVERRIDE_SNAPSHOT_BYTES)


def validate_generation_template_snapshot(value: object) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "identity"}
        or type(value.get("version")) is not int
        or value["version"] != 1
        or not isinstance(value.get("identity"), dict)
        or set(value["identity"]) != {"id", "type_key", "version", "checksum_sha256"}
    ):
        raise ValidationError(_("The generation template snapshot is invalid."))
    _validate_snapshot_value(value)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(encoded) > MAX_GENERATION_TEMPLATE_SNAPSHOT_BYTES:
        raise ValidationError(_("The generation template snapshot exceeds the allowed size."))


class ImmutableTemplateVersionError(Exception):
    """Raised when protected template history is updated or deleted."""


class InvalidTemplateLifecycleTransition(ValueError):
    """Raised when a template lifecycle transition is not declared."""


class TemplateVersionQuerySet(models.QuerySet["TemplateVersion"]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableTemplateVersionError(
            "Template versions cannot be updated through bulk application operations."
        )

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableTemplateVersionError(
            "Template versions cannot be deleted by the application."
        )

    def bulk_create(self, *args: Any, **kwargs: Any) -> list[TemplateVersion]:
        raise ImmutableTemplateVersionError(
            "Template versions cannot be created through bulk application operations."
        )

    def bulk_update(self, *args: Any, **kwargs: Any) -> int:
        raise ImmutableTemplateVersionError(
            "Template versions cannot be updated through bulk application operations."
        )


class TemplateVersionManager(models.Manager["TemplateVersion"]):
    def get_queryset(self) -> TemplateVersionQuerySet:
        return TemplateVersionQuerySet(self.model, using=self._db)


def _validate_report_value(value: object, *, depth: int = 0) -> None:
    if depth > MAX_VALIDATION_REPORT_DEPTH:
        raise ValidationError(_("The validation report is too deeply nested."))
    if isinstance(value, dict):
        if len(value) > MAX_VALIDATION_REPORT_ITEMS:
            raise ValidationError(_("The validation report has too many entries."))
        for key, nested_value in value.items():
            if not isinstance(key, str) or any(
                part in key.casefold() for part in _SENSITIVE_REPORT_KEY_PARTS
            ):
                raise ValidationError(_("The validation report contains an unsafe field."))
            _validate_report_value(nested_value, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > MAX_VALIDATION_REPORT_ITEMS:
            raise ValidationError(_("The validation report has too many entries."))
        for nested_value in value:
            _validate_report_value(nested_value, depth=depth + 1)
        return
    if isinstance(value, str) and len(value) <= MAX_VALIDATION_REPORT_STRING_LENGTH:
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValidationError(_("The validation report contains an unsupported value."))
    if value is None or isinstance(value, (bool, int, float)):
        return
    raise ValidationError(_("The validation report contains an unsupported value."))


def validate_validation_report(value: object) -> None:
    if not isinstance(value, dict):
        raise ValidationError(_("The validation report must be a structured object."))
    if value:
        allowed_keys = {"schema_version", "result", "categories", "counts"}
        if set(value) != allowed_keys:
            raise ValidationError(_("The validation report contains an unsafe field."))
        if value["schema_version"] != 1 or value["result"] not in {"valid", "invalid"}:
            raise ValidationError(_("The validation report contains an unsupported value."))
        categories = value["categories"]
        counts = value["counts"]
        if (
            not isinstance(categories, list)
            or any(
                not isinstance(item, str) or not _SAFE_REPORT_CODE.fullmatch(item)
                for item in categories
            )
            or not isinstance(counts, dict)
            or any(
                not isinstance(key, str)
                or not _SAFE_REPORT_CODE.fullmatch(key)
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 0
                or count > 1_000_000
                for key, count in counts.items()
            )
        ):
            raise ValidationError(_("The validation report contains an unsupported value."))
    _validate_report_value(value)
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValidationError(_("The validation report must be valid JSON.")) from error
    if len(encoded) > MAX_VALIDATION_REPORT_BYTES:
        raise ValidationError(_("The validation report exceeds the storage limit."))


class TemplateVersion(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded", _("Uploaded")
        VALID = "valid", _("Valid")
        INVALID = "invalid", _("Invalid")
        ACTIVE = "active", _("Active")
        INACTIVE = "inactive", _("Inactive")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type_key = models.CharField(max_length=64, editable=False)
    version = models.CharField(
        max_length=64,
        editable=False,
        validators=[RegexValidator(_VERSION_PATTERN)],
    )
    storage_key = models.CharField(
        max_length=255,
        unique=True,
        default="",
        blank=True,
        editable=False,
        validators=[RegexValidator(_STORAGE_KEY_PATTERN)],
    )
    original_filename = models.CharField(max_length=MAX_DISPLAY_FILENAME_LENGTH, editable=False)
    checksum_sha256 = models.CharField(
        max_length=64,
        editable=False,
        validators=[RegexValidator(r"^[0-9a-f]{64}$")],
    )
    byte_size = models.PositiveBigIntegerField(
        editable=False,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_TEMPLATE_BYTES)],
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADED)
    validation_report = models.JSONField(
        default=dict, blank=True, validators=[validate_validation_report]
    )
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_template_versions",
        editable=False,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, editable=False)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activated_template_versions",
        editable=False,
    )
    activated_at = models.DateTimeField(null=True, blank=True, editable=False)
    approval_reference = models.CharField(max_length=255, editable=False)

    objects = TemplateVersionManager()

    _IMMUTABLE_FIELDS = (
        "type_key",
        "version",
        "storage_key",
        "original_filename",
        "checksum_sha256",
        "byte_size",
        "uploader_id",
        "uploaded_at",
        "approval_reference",
    )
    _TRANSITIONS = {
        Status.UPLOADED: frozenset({Status.VALID, Status.INVALID}),
        Status.VALID: frozenset({Status.ACTIVE}),
        Status.INVALID: frozenset(),
        Status.ACTIVE: frozenset({Status.INACTIVE}),
        Status.INACTIVE: frozenset({Status.ACTIVE}),
    }

    class Meta:
        base_manager_name = "objects"
        ordering = ("type_key", "-uploaded_at", "id")
        indexes = [
            models.Index(
                fields=["type_key", "status", "-uploaded_at"],
                name="documents_template_lookup_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["type_key", "version"],
                name="documents_template_type_version_unique",
            ),
            models.UniqueConstraint(
                fields=["type_key"],
                condition=Q(status="active"),
                name="documents_one_active_template_per_type",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("uploaded", "valid", "invalid", "active", "inactive")),
                name="documents_template_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(checksum_sha256__regex=r"^[0-9a-f]{64}$"),
                name="documents_template_checksum_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    type_key__regex=(r"^(?:vds-[0-9]{2}|synthetic-[a-z0-9]+(?:-[a-z0-9]+)*)$")
                ),
                name="documents_template_type_key_format",
            ),
            models.CheckConstraint(
                condition=Q(version__regex=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"),
                name="documents_template_version_format",
            ),
            models.CheckConstraint(
                condition=Q(storage_key__regex=_STORAGE_KEY_PATTERN.pattern),
                name="documents_template_storage_key_format",
            ),
            models.CheckConstraint(
                condition=Q(
                    storage_key__startswith=Concat(
                        models.Value("templates/"),
                        models.F("type_key"),
                        models.Value("/"),
                        models.F("version"),
                        models.Value("/"),
                    )
                ),
                name="documents_template_storage_key_identity",
            ),
            models.CheckConstraint(
                condition=Q(original_filename__regex=r"^[^/\\\x00-\x1f\x7f]{1,150}$"),
                name="documents_template_display_filename_safe",
            ),
            models.CheckConstraint(
                condition=Q(byte_size__gte=1, byte_size__lte=MAX_TEMPLATE_BYTES),
                name="documents_template_size_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status__in=("active", "inactive"),
                        activated_by__isnull=False,
                        activated_at__isnull=False,
                    )
                    | Q(
                        status__in=("uploaded", "valid", "invalid"),
                        activated_by__isnull=True,
                        activated_at__isnull=True,
                    )
                ),
                name="documents_template_activation_metadata_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type_key}:{self.version} ({self.status})"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._transition_in_progress = False
        if not self.storage_key and self.type_key and self.version:
            try:
                self.storage_key = build_template_storage_key(self.type_key, self.version)
            except ValueError:
                # Field validation reports the unsafe registry/version components together.
                pass

    def clean(self) -> None:
        super().clean()
        try:
            document_registry.get(self.type_key)
        except UnknownDocumentTypeKey as error:
            raise ValidationError({"type_key": _("Unknown document type key.")}) from error
        if not self.version.strip():
            raise ValidationError({"version": _("A template version is required.")})
        if sanitize_template_display_filename(self.original_filename) != self.original_filename:
            raise ValidationError(
                {"original_filename": _("The template display filename must be sanitized.")}
            )
        if not _STORAGE_KEY_PATTERN.fullmatch(self.storage_key):
            raise ValidationError({"storage_key": _("The private storage key is invalid.")})
        expected_storage_prefix = f"templates/{self.type_key}/{self.version}/"
        if not self.storage_key.startswith(expected_storage_prefix):
            raise ValidationError(
                {"storage_key": _("The private storage key does not match this template.")}
            )
        if not self.approval_reference.strip():
            raise ValidationError({"approval_reference": _("An approval reference is required.")})

    def save(self, *args: Any, **kwargs: Any) -> None:
        transition_in_progress = getattr(self, "_transition_in_progress", False)
        if self._state.adding and self.status != self.Status.UPLOADED:
            raise InvalidTemplateLifecycleTransition("New templates must start in uploaded state.")
        if not self._state.adding:
            persisted = type(self).objects.get(pk=self.pk)
            changed_immutable = [
                field
                for field in self._IMMUTABLE_FIELDS
                if getattr(self, field) != getattr(persisted, field)
            ]
            if changed_immutable:
                raise ImmutableTemplateVersionError(
                    f"Immutable template fields changed: {', '.join(changed_immutable)}"
                )
            if (
                persisted.status != self.Status.UPLOADED
                and self.validation_report != persisted.validation_report
            ):
                raise ImmutableTemplateVersionError(
                    "A completed template validation report cannot change."
                )
            if self.status != persisted.status and not transition_in_progress:
                raise InvalidTemplateLifecycleTransition(
                    "Template status changes must use the lifecycle transition method."
                )
            if (self.activated_by_id, self.activated_at) != (
                persisted.activated_by_id,
                persisted.activated_at,
            ) and not transition_in_progress:
                raise ImmutableTemplateVersionError(
                    "Activation metadata can change only through a lifecycle transition."
                )
        self.full_clean()
        super().save(*args, **kwargs)

    def transition_to(self, status: Status, *, actor: AbstractBaseUser | None = None) -> None:
        if self._state.adding:
            raise InvalidTemplateLifecycleTransition("Only persisted templates can transition.")
        target = self.Status(status)
        with transaction.atomic():
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            current = self.Status(locked.status)
            if target == current:
                self.status = locked.status
                self.activated_by_id = locked.activated_by_id
                self.activated_at = locked.activated_at
                return
            if target not in self._TRANSITIONS[current]:
                raise InvalidTemplateLifecycleTransition(
                    f"Cannot transition from {current} to {target}."
                )
            if target == self.Status.ACTIVE:
                if actor is None:
                    raise InvalidTemplateLifecycleTransition("Activation requires an actor.")
                if locked.activated_at is None:
                    locked.activated_by_id = actor.pk
                    locked.activated_at = timezone.now()
            locked.status = target
            locked._transition_in_progress = True
            try:
                locked.save(update_fields=("status", "activated_by", "activated_at"))
            finally:
                locked._transition_in_progress = False
            self.status = locked.status
            self.activated_by_id = locked.activated_by_id
            self.activated_at = locked.activated_at

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableTemplateVersionError(
            "Template versions cannot be deleted by the application."
        )


class ImmutableDocumentDraftIdentityError(Exception):
    """Raised when durable draft identity is changed without an explicit migration."""


class DocumentDraftQuerySet(models.QuerySet["DocumentDraft"]):
    _IMMUTABLE_UPDATE_FIELDS = frozenset(
        {
            "id",
            "case",
            "case_id",
            "type_key",
            "schema_version",
            "created_by",
            "created_by_id",
            "created_at",
        }
    )

    def update(self, **kwargs: Any) -> int:
        if self._IMMUTABLE_UPDATE_FIELDS & set(kwargs):
            raise ImmutableDocumentDraftIdentityError(
                "Draft case, type, schema, creator, and creation time are immutable."
            )
        return super().update(**kwargs)


class DocumentDraftManager(models.Manager["DocumentDraft"]):
    def get_queryset(self) -> DocumentDraftQuerySet:
        return DocumentDraftQuerySet(self.model, using=self._db)


class DocumentDraft(models.Model):
    """Mutable, schema-bound document input kept separate from final snapshots."""

    class State(models.TextChoices):
        DRAFT = "draft", _("Draft")
        READY = "ready", _("Ready")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        "cases.CaseRecord",
        on_delete=models.PROTECT,
        related_name="document_drafts",
    )
    type_key = models.CharField(max_length=64)
    schema_version = models.CharField(
        max_length=16,
        validators=[RegexValidator(r"^v[1-9][0-9]*$")],
    )
    payload = models.JSONField(validators=[validate_document_draft_payload])
    state = models.CharField(max_length=16, choices=State.choices, default=State.DRAFT)
    revision = models.PositiveBigIntegerField(default=1, validators=[MinValueValidator(1)])
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_document_drafts",
        editable=False,
    )
    last_edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="edited_document_drafts",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    objects = DocumentDraftManager()

    _IMMUTABLE_IDENTITY_FIELDS = (
        "case_id",
        "type_key",
        "schema_version",
        "created_by_id",
        "created_at",
    )

    class Meta:
        ordering = ("-updated_at", "id")
        indexes = [
            models.Index(
                fields=["case", "state", "-updated_at"],
                name="doc_draft_case_state_idx",
            ),
            models.Index(
                fields=["type_key", "schema_version", "state"],
                name="doc_draft_type_schema_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "type_key", "schema_version"],
                name="documents_draft_case_type_schema_unique",
            ),
            models.CheckConstraint(
                condition=Q(state__in=("draft", "ready")),
                name="documents_draft_state_valid",
            ),
            models.CheckConstraint(
                condition=Q(revision__gte=1),
                name="documents_draft_revision_positive",
            ),
            models.CheckConstraint(
                condition=Q(
                    type_key__regex=(r"^(?:vds-[0-9]{2}|synthetic-[a-z0-9]+(?:-[a-z0-9]+)*)$")
                ),
                name="documents_draft_type_key_format",
            ),
            models.CheckConstraint(
                condition=Q(schema_version__regex=r"^v[1-9][0-9]*$"),
                name="documents_draft_schema_version_format",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type_key}:{self.schema_version} draft {self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            persisted = type(self).objects.only(*self._IMMUTABLE_IDENTITY_FIELDS).get(pk=self.pk)
            if any(
                getattr(self, field_name) != getattr(persisted, field_name)
                for field_name in self._IMMUTABLE_IDENTITY_FIELDS
            ):
                raise ImmutableDocumentDraftIdentityError(
                    "Draft case, type, schema, creator, and creation time are immutable."
                )
        self.full_clean()
        super().save(*args, **kwargs)


class ImmutableGeneratedDocumentError(Exception):
    """Raised when immutable generation history is mutated through application APIs."""


class GeneratedDocumentQuerySet(models.QuerySet["GeneratedDocument"]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableGeneratedDocumentError(
            "Generation attempts cannot be updated through bulk application operations."
        )

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableGeneratedDocumentError(
            "Generation attempts cannot be deleted by the application."
        )

    def bulk_create(self, *args: Any, **kwargs: Any) -> list[GeneratedDocument]:
        raise ImmutableGeneratedDocumentError(
            "Generation attempts must be created by the reservation service."
        )

    def bulk_update(self, *args: Any, **kwargs: Any) -> int:
        raise ImmutableGeneratedDocumentError(
            "Generation attempts cannot be updated through bulk application operations."
        )


class GeneratedDocumentManager(models.Manager["GeneratedDocument"]):
    def get_queryset(self) -> GeneratedDocumentQuerySet:
        return GeneratedDocumentQuerySet(self.model, using=self._db)


class GeneratedDocument(models.Model):
    """One immutable reservation plus its future one-way lifecycle outcome."""

    class Status(models.TextChoices):
        GENERATING = "generating", _("Generating")
        GENERATED = "generated", _("Generated")
        FAILED = "failed", _("Failed")

    class FailureCategory(models.TextChoices):
        TEMPLATE_INVALID = "template_invalid", _("Template invalid")
        CONTEXT_MISSING = "context_missing", _("Context missing")
        RENDER_ERROR = "render_error", _("Render error")
        STORAGE_ERROR = "storage_error", _("Storage error")
        INTEGRITY_ERROR = "integrity_error", _("Integrity error")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        "cases.CaseRecord",
        on_delete=models.PROTECT,
        related_name="generated_documents",
        editable=False,
    )
    type_key = models.CharField(max_length=64, editable=False)
    template_version = models.ForeignKey(
        TemplateVersion,
        on_delete=models.PROTECT,
        related_name="generation_attempts",
        editable=False,
    )
    schema_version = models.CharField(
        max_length=16,
        editable=False,
        validators=[RegexValidator(r"^v[1-9][0-9]*$")],
    )
    source_draft_id = models.UUIDField(editable=False)
    case_revision = models.PositiveBigIntegerField(
        editable=False, validators=[MinValueValidator(1)]
    )
    draft_revision = models.PositiveBigIntegerField(
        editable=False, validators=[MinValueValidator(1)]
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.GENERATING,
        editable=False,
    )
    input_snapshot = models.JSONField(
        editable=False, validators=[validate_generation_input_snapshot]
    )
    resolved_values_snapshot = models.JSONField(
        editable=False, validators=[validate_generation_resolved_snapshot]
    )
    override_snapshot = models.JSONField(
        editable=False, validators=[validate_generation_override_snapshot]
    )
    template_snapshot = models.JSONField(
        editable=False, validators=[validate_generation_template_snapshot]
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generated_document_attempts",
        editable=False,
    )
    reserved_at = models.DateTimeField(auto_now_add=True, editable=False)
    generated_at = models.DateTimeField(null=True, blank=True, editable=False)
    failed_at = models.DateTimeField(null=True, blank=True, editable=False)
    idempotency_key_hash = models.CharField(
        max_length=64,
        editable=False,
        validators=[RegexValidator(_SHA256_PATTERN)],
    )
    failure_category = models.CharField(
        max_length=32,
        choices=FailureCategory.choices,
        blank=True,
        default="",
        editable=False,
    )
    failure_correlation_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        editable=False,
        validators=[RegexValidator(_SAFE_CORRELATION_PATTERN)],
    )
    output_storage_key = models.CharField(
        max_length=500,
        blank=True,
        default="",
        editable=False,
        validators=[RegexValidator(_GENERATED_STORAGE_KEY_PATTERN)],
    )
    output_filename = models.CharField(
        max_length=MAX_DISPLAY_FILENAME_LENGTH,
        blank=True,
        default="",
        editable=False,
        validators=[RegexValidator(_GENERATED_FILENAME_PATTERN)],
    )
    output_size = models.PositiveBigIntegerField(null=True, blank=True, editable=False)
    output_checksum_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default="",
        editable=False,
        validators=[RegexValidator(r"^(?:|[0-9a-f]{64})$")],
    )

    objects = GeneratedDocumentManager()

    class Meta:
        ordering = ("-reserved_at", "id")
        indexes = [
            models.Index(
                fields=["case", "-reserved_at"],
                name="doc_gen_case_history_idx",
            ),
            models.Index(
                fields=["type_key", "status", "-reserved_at"],
                name="doc_generation_type_status_idx",
            ),
            models.Index(
                fields=["actor", "-reserved_at"],
                name="doc_gen_actor_history_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "idempotency_key_hash"],
                name="documents_generation_actor_idempotency_unique",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("generating", "generated", "failed")),
                name="documents_generation_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(type_key__regex=_GENERATION_TYPE_KEY_PATTERN),
                name="documents_generation_type_key_format",
            ),
            models.CheckConstraint(
                condition=Q(schema_version__regex=r"^v[1-9][0-9]*$"),
                name="documents_generation_schema_format",
            ),
            models.CheckConstraint(
                condition=Q(case_revision__gte=1, draft_revision__gte=1),
                name="documents_generation_revisions_positive",
            ),
            models.CheckConstraint(
                condition=Q(idempotency_key_hash__regex=_SHA256_PATTERN),
                name="documents_generation_idempotency_hash_valid",
            ),
            models.CheckConstraint(
                condition=Q(failure_correlation_id__regex=_SAFE_CORRELATION_PATTERN),
                name="documents_generation_failure_correlation_safe",
            ),
            models.CheckConstraint(
                condition=Q(output_storage_key__regex=_GENERATED_STORAGE_KEY_PATTERN),
                name="documents_generation_storage_key_safe",
            ),
            models.CheckConstraint(
                condition=(
                    Q(output_storage_key="")
                    | Q(
                        StartsWith(
                            Replace(
                                models.F("output_storage_key"),
                                models.Value("-"),
                                models.Value(""),
                            ),
                            Concat(
                                models.Value("generated/"),
                                Replace(
                                    Cast(models.F("case_id"), models.CharField()),
                                    models.Value("-"),
                                    models.Value(""),
                                ),
                                models.Value("/"),
                                Replace(
                                    Cast(models.F("id"), models.CharField()),
                                    models.Value("-"),
                                    models.Value(""),
                                ),
                                models.Value("/"),
                            ),
                        )
                    )
                ),
                name="documents_generation_storage_key_identity",
            ),
            models.CheckConstraint(
                condition=Q(output_filename__regex=_GENERATED_FILENAME_PATTERN),
                name="documents_generation_filename_safe",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status="generating",
                        generated_at__isnull=True,
                        failed_at__isnull=True,
                        failure_category="",
                        failure_correlation_id="",
                        output_storage_key="",
                        output_filename="",
                        output_size__isnull=True,
                        output_checksum_sha256="",
                    )
                    | Q(
                        status="generated",
                        generated_at__isnull=False,
                        failed_at__isnull=True,
                        failure_category="",
                        failure_correlation_id="",
                        output_size__isnull=False,
                        output_size__gte=1,
                        output_checksum_sha256__regex=_SHA256_PATTERN,
                    )
                    & ~Q(output_storage_key="")
                    & ~Q(output_filename="")
                    | Q(
                        status="failed",
                        generated_at__isnull=True,
                        failed_at__isnull=False,
                        failure_category__in=(
                            "template_invalid",
                            "context_missing",
                            "render_error",
                            "storage_error",
                            "integrity_error",
                        ),
                        output_storage_key="",
                        output_filename="",
                        output_size__isnull=True,
                        output_checksum_sha256="",
                    )
                    & ~Q(failure_correlation_id="")
                ),
                name="documents_generation_status_metadata_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type_key} generation {self.pk} ({self.status})"

    def clean(self) -> None:
        super().clean()
        if self.template_version_id and self.template_version.type_key != self.type_key:
            raise ValidationError(
                {"template_version": _("The template does not match the document type.")}
            )
        identity = (
            self.template_snapshot.get("identity", {})
            if isinstance(self.template_snapshot, dict)
            else None
        )
        if self.template_version_id and identity != {
            "id": str(self.template_version_id),
            "type_key": self.template_version.type_key,
            "version": self.template_version.version,
            "checksum_sha256": self.template_version.checksum_sha256,
        }:
            raise ValidationError(
                {"template_snapshot": _("The template snapshot does not match its reference.")}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableGeneratedDocumentError(
                "Generation attempts cannot be changed through the model API."
            )
        if self.status != self.Status.GENERATING:
            raise ImmutableGeneratedDocumentError("New generation attempts must be generating.")
        self.full_clean(validate_constraints=False)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableGeneratedDocumentError(
            "Generation attempts cannot be deleted by the application."
        )
