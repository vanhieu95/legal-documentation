from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import Q

from apps.cases.models import Court, Entity, EntityAddress, Official

FIELD_CONTROL = "field-control"


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
            "is_active",
        )

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
            "is_active",
        )
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}


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
            "is_active",
        )
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_to": forms.DateInput(attrs={"type": "date"}),
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
        fields = ("entity", "home_court", "title", "position", "is_active")

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
