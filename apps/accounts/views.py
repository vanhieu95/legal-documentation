from __future__ import annotations

from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.forms import (
    GENERIC_AUTHENTICATION_FAILURE,
    AdministratorAuthenticationForm,
)
from apps.accounts.policies import ApplicationPermission, application_permission_required


def _safe_local_destination(request: HttpRequest, candidate: str | None) -> str | None:
    if not candidate or "\\" in candidate:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    if not url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return None
    return candidate


@never_cache
@require_http_methods(["GET", "POST"])
def login(request: HttpRequest) -> HttpResponse:
    submitted_destination = request.POST.get(REDIRECT_FIELD_NAME)
    requested_destination = submitted_destination or request.GET.get(REDIRECT_FIELD_NAME)
    safe_destination = _safe_local_destination(request, requested_destination)

    if request.method == "POST":
        submitted_form = AdministratorAuthenticationForm(request=request, data=request.POST)
        if submitted_form.is_valid():
            auth_login(request, submitted_form.get_user())
            return redirect(safe_destination or reverse("accounts:dashboard"))
        form = AdministratorAuthenticationForm(request=request)
        authentication_error = GENERIC_AUTHENTICATION_FAILURE
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
    auth_logout(request)
    return redirect(settings.LOGIN_URL)


@never_cache
@application_permission_required(ApplicationPermission.VIEW_CASES)
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/dashboard_placeholder.html")
