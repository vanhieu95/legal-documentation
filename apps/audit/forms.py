from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.audit.actions import AuditAction, AuditOutcome, AuditTargetType
from apps.audit.selectors import (
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT,
    MAX_PAGE_SIZE,
    AuditListFilters,
    parse_audit_list_filters,
)


def _as_utc_datetime(value: datetime) -> datetime:
    """Treat datetime-local wall-clock values as UTC audit instants."""
    wall_clock = value.replace(tzinfo=None) if value.tzinfo is not None else value
    return wall_clock.replace(tzinfo=UTC)


class AuditEventFilterForm(forms.Form):
    """Read-only GET filters for authorized audit browsing."""

    action = forms.ChoiceField(
        label=_("Action"),
        required=False,
        choices=[("", _("All actions"))] + [(value, value) for value in AuditAction],
    )
    outcome = forms.ChoiceField(
        label=_("Outcome"),
        required=False,
        choices=[("", _("All outcomes"))] + [(value, value) for value in AuditOutcome],
    )
    actor = forms.CharField(
        label=_("Actor"),
        required=False,
        max_length=36,
    )
    target_type = forms.ChoiceField(
        label=_("Target type"),
        required=False,
        choices=[("", _("All target types"))] + [(value, value) for value in AuditTargetType],
    )
    target_id = forms.CharField(
        label=_("Target identifier"),
        required=False,
        max_length=128,
    )
    correlation_id = forms.CharField(
        label=_("Correlation ID"),
        required=False,
        max_length=128,
    )
    occurred_from = forms.DateTimeField(
        label=_("From"),
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d"],
        widget=forms.DateTimeInput(
            attrs={
                "class": "field-control",
                "type": "datetime-local",
            }
        ),
    )
    occurred_to = forms.DateTimeField(
        label=_("To"),
        required=False,
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d"],
        widget=forms.DateTimeInput(
            attrs={
                "class": "field-control",
                "type": "datetime-local",
            }
        ),
    )
    sort = forms.ChoiceField(
        label=_("Sort"),
        required=False,
        choices=[
            (DEFAULT_SORT, _("Newest first")),
            ("occurred_at", _("Oldest first")),
            ("action", _("Action (A–Z)")),
            ("-action", _("Action (Z–A)")),
            ("outcome", _("Outcome (A–Z)")),
            ("-outcome", _("Outcome (Z–A)")),
            ("target_type", _("Target type (A–Z)")),
            ("-target_type", _("Target type (Z–A)")),
            ("correlation_id", _("Correlation ID (A–Z)")),
            ("-correlation_id", _("Correlation ID (Z–A)")),
        ],
        initial=DEFAULT_SORT,
    )
    page_size = forms.IntegerField(
        label=_("Page size"),
        required=False,
        min_value=1,
        max_value=MAX_PAGE_SIZE,
        initial=DEFAULT_PAGE_SIZE,
    )
    page = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput())

    def clean_page(self) -> int:
        page = self.cleaned_data.get("page")
        return page or 1

    def clean_page_size(self) -> int:
        page_size = self.cleaned_data.get("page_size")
        return page_size or DEFAULT_PAGE_SIZE

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name in {"occurred_from", "occurred_to"}:
                continue
            widget = field.widget
            widget.attrs.setdefault("class", "field-control")

    @property
    def selector_errors(self) -> list[str]:
        return list(getattr(self, "_selector_errors", ()))

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        query = dict(self.data.items())
        if occurred_from := cleaned_data.get("occurred_from"):
            query["occurred_from"] = _as_utc_datetime(occurred_from).isoformat()
        if occurred_to := cleaned_data.get("occurred_to"):
            query["occurred_to"] = _as_utc_datetime(occurred_to).isoformat()
        filters, errors = parse_audit_list_filters(query)
        self._selector_errors = errors
        if errors:
            raise forms.ValidationError(errors[0])
        cleaned_data["filters"] = filters
        return cleaned_data

    def to_querydict(self, *, page: int | None = None) -> dict[str, str]:
        """Build canonical query parameters for links and form state."""
        if not self.is_valid():
            return {}
        filters: AuditListFilters = self.cleaned_data["filters"]
        params: dict[str, str] = {}
        if filters.action:
            params["action"] = filters.action
        if filters.outcome:
            params["outcome"] = filters.outcome
        if filters.actor_id:
            params["actor"] = filters.actor_id
        if filters.target_type:
            params["target_type"] = filters.target_type
        if filters.target_id:
            params["target_id"] = filters.target_id
        if filters.correlation_id:
            params["correlation_id"] = filters.correlation_id
        if filters.occurred_from is not None:
            params["occurred_from"] = filters.occurred_from.isoformat()
        if filters.occurred_to is not None:
            params["occurred_to"] = filters.occurred_to.isoformat()
        if filters.sort != DEFAULT_SORT:
            params["sort"] = filters.sort
        if filters.page_size != DEFAULT_PAGE_SIZE:
            params["page_size"] = str(filters.page_size)
        params["page"] = str(page if page is not None else filters.page)
        return params
