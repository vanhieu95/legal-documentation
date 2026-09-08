from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

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


class CaseRecordEditForm(CaseRecordForm):
    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput,
        label=_("Expected revision"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.instance.pk:
            self.initial["expected_revision"] = self.instance.revision


class CaseTransitionForm(forms.Form):
    expected_revision = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput,
        label=_("Expected revision"),
    )


class CaseArchiveForm(CaseTransitionForm):
    reason = forms.CharField(
        max_length=500,
        strip=True,
        label=_("Archive reason"),
        widget=forms.Textarea(attrs={"class": FIELD_CONTROL, "rows": 4}),
    )


class CaseRestoreForm(CaseTransitionForm):
    pass


class CaseParticipantForm(ReferenceModelForm):
    class Meta:
        model = CaseParticipant
        fields = (
            "entity",
            "role",
            "case_address",
            "case_workplace",
            "case_contact",
            "ordering",
            "effective_from",
            "effective_to",
        )
        widgets = {
            "case_address": forms.Textarea(attrs={"rows": 3}),
            "case_contact": forms.Textarea(attrs={"rows": 3}),
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "entity": _("Entity"),
            "role": _("Participant role"),
            "case_address": _("Case-specific address"),
            "case_workplace": _("Case-specific workplace"),
            "case_contact": _("Case-specific contact"),
            "ordering": _("Ordering"),
            "effective_from": _("Effective from"),
            "effective_to": _("Effective to"),
        }

    def __init__(self, *args: Any, case: CaseRecord, **kwargs: Any) -> None:
        self.case = case
        super().__init__(*args, **kwargs)
        queryset = Entity.objects.filter(is_active=True)
        if self.instance.pk and self.instance.entity_id:
            queryset = Entity.objects.filter(Q(is_active=True) | Q(pk=self.instance.entity_id))
        entity_field = cast("forms.ModelChoiceField[Entity]", self.fields["entity"])
        entity_field.queryset = queryset.order_by("legal_name")


class RepresentationForm(ReferenceModelForm):
    class Meta:
        model = Representation
        fields = (
            "representative_entity",
            "represented_participant",
            "representation_type",
            "authority_reference",
            "authority_date",
            "description",
        )
        widgets = {
            "authority_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "representative_entity": _("Representative"),
            "represented_participant": _("Represented participant"),
            "representation_type": _("Representation type"),
            "authority_reference": _("Authority reference"),
            "authority_date": _("Authority date"),
            "description": _("Description"),
        }

    def __init__(self, *args: Any, case: CaseRecord, **kwargs: Any) -> None:
        self.case = case
        super().__init__(*args, **kwargs)
        entity_queryset = Entity.objects.filter(is_active=True)
        participant_queryset = CaseParticipant.objects.filter(case=case, is_active=True)
        if self.instance.pk:
            entity_queryset = Entity.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.representative_entity_id)
            )
            participant_queryset = CaseParticipant.objects.filter(
                Q(case=case, is_active=True) | Q(pk=self.instance.represented_participant_id)
            )
        representative_field = cast(
            "forms.ModelChoiceField[Entity]", self.fields["representative_entity"]
        )
        participant_field = cast(
            "forms.ModelChoiceField[CaseParticipant]", self.fields["represented_participant"]
        )
        representative_field.queryset = entity_queryset.order_by("legal_name")
        participant_field.queryset = participant_queryset.order_by("ordering", "id")


class ScopedParticipantFormSet(forms.BaseModelFormSet):  # type: ignore[type-arg]
    def __init__(self, *args: Any, case: CaseRecord, **kwargs: Any) -> None:
        self.case = case
        kwargs["queryset"] = CaseParticipant.objects.filter(case=case, is_active=True)
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index: int | None) -> dict[str, Any]:
        kwargs = super().get_form_kwargs(index)
        kwargs["case"] = self.case
        return kwargs

    def save_new(self, form: forms.ModelForm[Any], commit: bool = True) -> CaseParticipant:
        form.instance.case = self.case
        return cast(CaseParticipant, super().save_new(form, commit=commit))

    def delete_existing(self, obj: CaseParticipant, commit: bool = True) -> None:
        if commit:
            obj.is_active = False
            obj.save(update_fields=["is_active"])


class ScopedRepresentationFormSet(forms.BaseModelFormSet):  # type: ignore[type-arg]
    def __init__(self, *args: Any, case: CaseRecord, **kwargs: Any) -> None:
        self.case = case
        kwargs["queryset"] = Representation.objects.filter(case=case, is_active=True)
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index: int | None) -> dict[str, Any]:
        kwargs = super().get_form_kwargs(index)
        kwargs["case"] = self.case
        return kwargs

    def save_new(self, form: forms.ModelForm[Any], commit: bool = True) -> Representation:
        form.instance.case = self.case
        return cast(Representation, super().save_new(form, commit=commit))

    def delete_existing(self, obj: Representation, commit: bool = True) -> None:
        if commit:
            obj.is_active = False
            obj.save(update_fields=["is_active"])


ParticipantFormSet = forms.modelformset_factory(
    CaseParticipant,
    form=CaseParticipantForm,
    formset=ScopedParticipantFormSet,
    extra=1,
    can_delete=True,
)
RepresentationFormSet = forms.modelformset_factory(
    Representation,
    form=RepresentationForm,
    formset=ScopedRepresentationFormSet,
    extra=1,
    can_delete=True,
)


def participant_formset(
    *, case: CaseRecord, data: dict[str, str] | None = None
) -> ScopedParticipantFormSet:
    return cast(
        ScopedParticipantFormSet,
        ParticipantFormSet(data=data, case=case, prefix="participants"),
    )


def representation_formset(
    *, case: CaseRecord, data: dict[str, str] | None = None
) -> ScopedRepresentationFormSet:
    return cast(
        ScopedRepresentationFormSet,
        RepresentationFormSet(data=data, case=case, prefix="representations"),
    )


class CaseOfficialAssignmentForm(ReferenceModelForm):
    class Meta:
        model = CaseOfficialAssignment
        fields = ("official", "role", "ordering", "effective_from", "effective_to")
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "official": _("Official"),
            "role": _("Procedural role"),
            "ordering": _("Ordering"),
            "effective_from": _("Effective from"),
            "effective_to": _("Effective to"),
        }

    def __init__(self, *args: Any, case: CaseRecord, **kwargs: Any) -> None:
        self.case = case
        super().__init__(*args, **kwargs)
        queryset = Official.objects.filter(home_court=case.court, is_active=True)
        if self.instance.pk and self.instance.official_id:
            queryset = Official.objects.filter(
                Q(home_court=case.court, is_active=True) | Q(pk=self.instance.official_id)
            )
        official_field = cast("forms.ModelChoiceField[Official]", self.fields["official"])
        official_field.queryset = queryset.order_by("entity__legal_name")


class HearingForm(ReferenceModelForm):
    class Meta:
        model = Hearing
        fields = ("instance_level", "scheduled_at", "location", "status")
        widgets = {"scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}
        labels = {
            "instance_level": _("Instance level"),
            "scheduled_at": _("Scheduled date and time"),
            "location": _("Location"),
            "status": _("Status"),
        }

    def __init__(self, *args: Any, case: CaseRecord, **kwargs: Any) -> None:
        self.case = case
        super().__init__(*args, **kwargs)


class ScopedAssignmentFormSet(forms.BaseModelFormSet):  # type: ignore[type-arg]
    def __init__(self, *args: Any, case: CaseRecord, **kwargs: Any) -> None:
        self.case = case
        kwargs["queryset"] = CaseOfficialAssignment.objects.filter(case=case, is_active=True)
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index: int | None) -> dict[str, Any]:
        kwargs = super().get_form_kwargs(index)
        kwargs["case"] = self.case
        return kwargs

    def save_new(self, form: forms.ModelForm[Any], commit: bool = True) -> CaseOfficialAssignment:
        form.instance.case = self.case
        return cast(CaseOfficialAssignment, super().save_new(form, commit=commit))

    def delete_existing(self, obj: CaseOfficialAssignment, commit: bool = True) -> None:
        if commit:
            obj.is_active = False
            obj.save(update_fields=["is_active"])


class ScopedHearingFormSet(forms.BaseModelFormSet):  # type: ignore[type-arg]
    def __init__(self, *args: Any, case: CaseRecord, **kwargs: Any) -> None:
        self.case = case
        kwargs["queryset"] = Hearing.objects.filter(case=case)
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index: int | None) -> dict[str, Any]:
        kwargs = super().get_form_kwargs(index)
        kwargs["case"] = self.case
        return kwargs

    def save_new(self, form: forms.ModelForm[Any], commit: bool = True) -> Hearing:
        form.instance.case = self.case
        return cast(Hearing, super().save_new(form, commit=commit))

    def delete_existing(self, obj: Hearing, commit: bool = True) -> None:
        if commit:
            obj.status = Hearing.Status.CANCELLED
            obj.save(update_fields=["status", "updated_at"])


AssignmentFormSet = forms.modelformset_factory(
    CaseOfficialAssignment,
    form=CaseOfficialAssignmentForm,
    formset=ScopedAssignmentFormSet,
    extra=1,
    can_delete=True,
)
HearingFormSet = forms.modelformset_factory(
    Hearing,
    form=HearingForm,
    formset=ScopedHearingFormSet,
    extra=1,
    can_delete=True,
)


def assignment_formset(
    *, case: CaseRecord, data: dict[str, str] | None = None
) -> ScopedAssignmentFormSet:
    return cast(
        ScopedAssignmentFormSet,
        AssignmentFormSet(data=data, case=case, prefix="assignments"),
    )


def hearing_formset(
    *, case: CaseRecord, data: dict[str, str] | None = None
) -> ScopedHearingFormSet:
    return cast(
        ScopedHearingFormSet,
        HearingFormSet(data=data, case=case, prefix="hearings"),
    )
