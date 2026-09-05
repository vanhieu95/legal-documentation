from __future__ import annotations

from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.policies import ApplicationPermission, application_permission_required
from apps.audit.forms import AuditEventFilterForm
from apps.audit.selectors import (
    AuditListFilters,
    AuditListPage,
    list_audit_events,
    parse_audit_list_filters,
)


def _is_htmx_request(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _empty_page(filters: AuditListFilters) -> AuditListPage:
    return AuditListPage(
        items=(),
        page=1,
        page_count=0,
        total_count=0,
        page_size=filters.page_size,
        sort=filters.sort,
        filters=filters,
    )


def _page_url(form: AuditEventFilterForm, page: int) -> str:
    if form.is_valid():
        return f"?{urlencode(form.to_querydict(page=page))}"
    return f"?page={page}"


@never_cache
@require_GET
@application_permission_required(ApplicationPermission.VIEW_AUDIT)
def audit_list(request: HttpRequest) -> HttpResponse:
    """Render authorized read-only audit browsing for full-page and HTMX requests."""
    form = AuditEventFilterForm(request.GET)
    validation_errors: list[str] = []
    if form.is_valid():
        audit_page = list_audit_events(form.cleaned_data["filters"])
    else:
        filters, selector_errors = parse_audit_list_filters(request.GET)
        validation_errors = [
            *(str(error) for error in form.non_field_errors()),
            *selector_errors,
            *(str(error) for errors in form.errors.values() for error in errors),
        ]
        audit_page = _empty_page(filters)

    previous_page_url = _page_url(form, audit_page.page - 1) if audit_page.page > 1 else None
    next_page_url = (
        _page_url(form, audit_page.page + 1)
        if audit_page.page_count and audit_page.page < audit_page.page_count
        else None
    )

    context = {
        "page_title": gettext("Audit log"),
        "form": form,
        "audit_page": audit_page,
        "validation_errors": validation_errors,
        "active_view_name": "audit:list",
        "previous_page_url": previous_page_url,
        "next_page_url": next_page_url,
    }
    template_name = "audit/_audit_results.html" if _is_htmx_request(request) else "audit/list.html"
    response = render(request, template_name, context)
    response["Vary"] = "HX-Request"
    return response
