from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.cases.models import CaseRecord, Court, Entity, EntityAddress, Official

FIELD_CONTROL = "field-control"


class ReferenceListFilterForm(forms.Form):
    q = forms.CharField(
        label=_("Search"),
        required=False,
        max_length=100,
        widget=forms.SearchInput(attrs={"class": FIELD_CONTROL, "autocomplete": "off"}),
    )
    state = forms.ChoiceField(
        label=_("State"),
        required=False,
        choices=(("active", _("Active")), ("inactive", _("Inactive")), ("all", _("All"))),
        initial="active",
        widget=forms.Select(attrs={"class": FIELD_CONTROL}),
    )
    page = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput())

    def clean_state(self) -> str:
        return self.cleaned_data.get("state") or "active"

    def clean_page(self) -> int:
        return self.cleaned_data.get("page") or 1


class ReferenceModelForm(forms.ModelForm):  # type: ignore[type-arg]
    """Apply the shared accessible control styling to reference forms."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", FIELD_CONTROL)


class CourtForm(ReferenceModelForm):
    class Meta:
        model = Court
        fields = (
            "code",
            "full_name",
            "short_name",
            "level",
            "address",
            "superior_court",
        )
        labels = {
            "code": _("Court code"),
            "full_name": _("Full court name"),
            "short_name": _("Short court name"),
            "level": _("Court level"),
            "address": _("Court address"),
            "superior_court": _("Superior court"),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        queryset = Court.objects.filter(is_active=True)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
            if self.instance.superior_court_id:
                queryset = Court.objects.filter(
                    Q(is_active=True) | Q(pk=self.instance.superior_court_id)
                ).exclude(pk=self.instance.pk)
        superior_field = cast("forms.ModelChoiceField[Court]", self.fields["superior_court"])
        superior_field.queryset = queryset.order_by("full_name")


class EntityForm(ReferenceModelForm):
    class Meta:
        model = Entity
        fields = (
            "kind",
            "legal_name",
            "display_name",
            "identity_document_number",
            "registration_number",
            "date_of_birth",
            "organization_type",
        )
        widgets = {
            "identity_document_number": forms.TextInput(attrs={"autocomplete": "off"}),
            "registration_number": forms.TextInput(attrs={"autocomplete": "off"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "kind": _("Entity kind"),
            "legal_name": _("Authoritative legal name"),
            "display_name": _("Display name"),
            "identity_document_number": _("Identity document number"),
            "registration_number": _("Registration number"),
            "date_of_birth": _("Date of birth"),
            "organization_type": _("Organization type"),
        }


class EntityAddressForm(ReferenceModelForm):
    class Meta:
        model = EntityAddress
        fields = (
            "entity",
            "kind",
            "full_address",
            "province",
            "district",
            "ward",
            "valid_from",
            "valid_to",
        )
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "entity": _("Entity"),
            "kind": _("Address kind"),
            "full_address": _("Full legal address"),
            "province": _("Province or municipality"),
            "district": _("District"),
            "ward": _("Ward or commune"),
            "valid_from": _("Valid from"),
            "valid_to": _("Valid to"),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        queryset = Entity.objects.filter(is_active=True)
        if self.instance.pk and self.instance.entity_id:
            queryset = Entity.objects.filter(Q(is_active=True) | Q(pk=self.instance.entity_id))
        entity_field = cast("forms.ModelChoiceField[Entity]", self.fields["entity"])
        entity_field.queryset = queryset.order_by("legal_name")


class OfficialForm(ReferenceModelForm):
    class Meta:
        model = Official
        fields = ("entity", "home_court", "title", "position")
        labels = {
            "entity": _("Individual"),
            "home_court": _("Home court"),
            "title": _("Title"),
            "position": _("Position"),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        entity_queryset = Entity.objects.filter(kind=Entity.Kind.INDIVIDUAL, is_active=True)
        court_queryset = Court.objects.filter(is_active=True)
        if self.instance.pk:
            entity_queryset = Entity.objects.filter(
                Q(kind=Entity.Kind.INDIVIDUAL, is_active=True) | Q(pk=self.instance.entity_id)
            )
            court_queryset = Court.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.home_court_id)
            )
        entity_field = cast("forms.ModelChoiceField[Entity]", self.fields["entity"])
        home_court_field = cast("forms.ModelChoiceField[Court]", self.fields["home_court"])
        entity_field.queryset = entity_queryset.order_by("legal_name")
        home_court_field.queryset = court_queryset.order_by("full_name")


class CaseRecordForm(ReferenceModelForm):
    class Meta:
        model = CaseRecord
        fields = (
            "internal_reference",
            "court",
            "matter_type",
            "procedural_stage",
            "acceptance_number",
            "acceptance_year",
            "acceptance_date",
            "acceptance_type_code",
        )
        widgets = {"acceptance_date": forms.DateInput(attrs={"type": "date"})}
        labels = {
            "internal_reference": _("Internal reference"),
            "court": _("Court"),
            "matter_type": _("Matter type"),
            "procedural_stage": _("Procedural stage"),
            "acceptance_number": _("Acceptance number"),
            "acceptance_year": _("Acceptance year"),
            "acceptance_date": _("Acceptance date"),
            "acceptance_type_code": _("Acceptance type code"),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        queryset = Court.objects.filter(is_active=True)
        if self.instance.pk and self.instance.court_id:
            queryset = Court.objects.filter(Q(is_active=True) | Q(pk=self.instance.court_id))
        court_field = cast("forms.ModelChoiceField[Court]", self.fields["court"])
        court_field.queryset = queryset.order_by("full_name")
