from __future__ import annotations

from typing import Any

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _

from apps.documents.limits import MAX_TEMPLATE_BYTES
from apps.documents.models import DocumentDraft, TemplateVersion

_IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9_-]{43}$"


class TemplateUploadForm(forms.Form):
    version = forms.RegexField(
        regex=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
        max_length=64,
        label=_("Template version"),
        help_text=_("Use a unique controlled version, for example v1.0."),
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    approval_reference = forms.CharField(
        max_length=255,
        label=_("Approval note or reference"),
        help_text=_("This records provenance and does not activate the template."),
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    template_file = forms.FileField(
        label=_("DOCX template"),
        help_text=_("Maximum compressed file size: 10 MiB."),
        widget=forms.ClearableFileInput(attrs={"accept": ".docx"}),
    )

    def clean_template_file(self) -> UploadedFile[Any]:
        uploaded = self.cleaned_data["template_file"]
        if uploaded.size > MAX_TEMPLATE_BYTES:
            raise forms.ValidationError(_("The uploaded file exceeds the 10 MiB limit."))
        if not uploaded.name.casefold().endswith(".docx"):
            raise forms.ValidationError(_("Select a DOCX file."))
        return uploaded


class TemplateTransitionForm(forms.Form):
    expected_status = forms.ChoiceField(
        choices=TemplateVersion.Status.choices,
        widget=forms.HiddenInput,
    )
    expected_active_id = forms.UUIDField(required=False, widget=forms.HiddenInput)


class DocumentDraftControlForm(forms.Form):
    draft_id = forms.UUIDField(required=False, widget=forms.HiddenInput)
    revision = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput)
    schema_version = forms.RegexField(
        regex=r"^v[1-9][0-9]*$", required=False, widget=forms.HiddenInput
    )
    state = forms.ChoiceField(choices=DocumentDraft.State.choices, widget=forms.HiddenInput)


class GenerationConfirmationForm(forms.Form):
    intent = forms.CharField(widget=forms.HiddenInput, initial="generate")
    draft_id = forms.UUIDField(widget=forms.HiddenInput)
    expected_case_revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    expected_draft_revision = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    schema_version = forms.RegexField(regex=r"^v[1-9][0-9]*$", widget=forms.HiddenInput)
    expected_template_id = forms.UUIDField(widget=forms.HiddenInput)
    idempotency_key = forms.RegexField(
        regex=_IDEMPOTENCY_KEY_PATTERN,
        min_length=43,
        max_length=43,
        widget=forms.HiddenInput,
    )
    confirmed = forms.BooleanField(
        label=_("I confirm the reviewed draft should be generated with this template version."),
    )

    def clean_intent(self) -> str:
        intent = self.cleaned_data["intent"]
        if intent != "generate":
            raise forms.ValidationError(_("The generation confirmation is invalid."))
        return intent


class GenerationRetryForm(forms.Form):
    attempt_id = forms.UUIDField(widget=forms.HiddenInput)
    idempotency_key = forms.RegexField(
        regex=_IDEMPOTENCY_KEY_PATTERN,
        min_length=43,
        max_length=43,
        widget=forms.HiddenInput,
    )
