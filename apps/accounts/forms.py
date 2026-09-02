from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts.policies import application_access_policy

GENERIC_AUTHENTICATION_FAILURE = _("Unable to sign in with the credentials provided.")


class AdministratorAuthenticationForm(AuthenticationForm):
    """Authenticate only principals admitted by the central application policy."""

    username = forms.CharField(
        label=_("Username"),
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "class": "field-control",
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "class": "field-control",
            }
        ),
    )
    error_messages = {
        "invalid_login": GENERIC_AUTHENTICATION_FAILURE,
        "inactive": GENERIC_AUTHENTICATION_FAILURE,
    }

    def confirm_login_allowed(self, user: User) -> None:
        if not application_access_policy.is_application_administrator(user):
            raise ValidationError(
                GENERIC_AUTHENTICATION_FAILURE,
                code="invalid_login",
            )
