from __future__ import annotations

from urllib.parse import urlencode

from typing import cast

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.audit import (
    record_identity_login_failure,
    record_identity_login_success,
    record_identity_logout,
)
from apps.accounts.forms import (
    AUDIT_REASON_INACTIVE_ACCOUNT,
    AUDIT_REASON_NOT_ADMINISTRATOR,
    GENERIC_AUTHENTICATION_FAILURE,
    AdministratorAuthenticationForm,
)
from apps.accounts.policies import ApplicationPermission, application_permission_required
from apps.accounts.sessions import establish_session_timestamps, safe_local_destination
from apps.audit.actions import AuditOutcome


@never_cache
@require_http_methods(["GET", "POST"])
def login(request: HttpRequest) -> HttpResponse:
    submitted_destination = request.POST.get(REDIRECT_FIELD_NAME)
    requested_destination = submitted_destination or request.GET.get(REDIRECT_FIELD_NAME)
    safe_destination = safe_local_destination(request, requested_destination)

    if request.method == "POST":
        submitted_form = AdministratorAuthenticationForm(request=request, data=request.POST)
        if submitted_form.is_valid():
            authenticated_user = submitted_form.get_user()
            record_identity_login_success(request=request, actor=authenticated_user)
            auth_login(request, authenticated_user)
            establish_session_timestamps(request)
            return redirect(safe_destination or reverse("accounts:dashboard"))
        form = AdministratorAuthenticationForm(request=request)
        reason_code = submitted_form.audit_failure_reason_code
        outcome = (
            AuditOutcome.DENIED
            if reason_code in {AUDIT_REASON_INACTIVE_ACCOUNT, AUDIT_REASON_NOT_ADMINISTRATOR}
            else AuditOutcome.FAILURE
        )
        record_identity_login_failure(
            request=request,
            reason_code=reason_code,
            outcome=outcome,
        )
        authentication_error = str(GENERIC_AUTHENTICATION_FAILURE)
    else:
        form = AdministratorAuthenticationForm(request=request)
        authentication_error = ""

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "authentication_error": authentication_error,
            REDIRECT_FIELD_NAME: safe_destination or "",
        },
    )


@never_cache
@require_POST
@login_required
def logout(request: HttpRequest) -> HttpResponse:
    record_identity_logout(request=request, actor=cast(User, request.user))
    auth_logout(request)
    return redirect(settings.LOGIN_URL)


@never_cache
@application_permission_required(ApplicationPermission.VIEW_CASES)
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/dashboard_placeholder.html")


@never_cache
@require_GET
def session_expired(request: HttpRequest) -> HttpResponse:
    destination = safe_local_destination(request, request.GET.get(REDIRECT_FIELD_NAME))
    login_url = reverse("accounts:login")
    if destination:
        login_url = f"{login_url}?{urlencode({REDIRECT_FIELD_NAME: destination})}"
    return render(
        request,
        "accounts/session_expired.html",
        {"reauthentication_url": login_url},
    )
