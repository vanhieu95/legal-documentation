from __future__ import annotations

from typing import Any

from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _

from apps.documents.limits import MAX_TEMPLATE_BYTES


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
