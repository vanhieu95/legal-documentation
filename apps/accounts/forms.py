from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts.policies import application_access_policy

GENERIC_AUTHENTICATION_FAILURE = _("Unable to sign in with the credentials provided.")
AUDIT_REASON_INVALID_CREDENTIALS = "invalid_credentials"
AUDIT_REASON_INACTIVE_ACCOUNT = "inactive_account"
AUDIT_REASON_NOT_ADMINISTRATOR = "not_administrator"


class AdministratorAuthenticationForm(AuthenticationForm):
    """Authenticate only principals admitted by the central application policy."""

    audit_failure_reason_code: str = AUDIT_REASON_INVALID_CREDENTIALS

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

    def clean(self) -> dict[str, object]:
        self.audit_failure_reason_code = AUDIT_REASON_INVALID_CREDENTIALS
        username = self.data.get("username")
        password = self.data.get("password")
        if isinstance(username, str) and isinstance(password, str) and username and password:
            try:
                candidate = User.objects.get(username=username)
            except User.DoesNotExist:
                pass
            else:
                if not candidate.is_active and candidate.check_password(password):
                    self.audit_failure_reason_code = AUDIT_REASON_INACTIVE_ACCOUNT
        return super().clean()

    def confirm_login_allowed(self, user: User) -> None:
        if not user.is_active:
            self.audit_failure_reason_code = AUDIT_REASON_INACTIVE_ACCOUNT
            raise ValidationError(
                GENERIC_AUTHENTICATION_FAILURE,
                code="inactive",
            )
        if not application_access_policy.is_application_administrator(user):
            self.audit_failure_reason_code = AUDIT_REASON_NOT_ADMINISTRATOR
            raise ValidationError(
                GENERIC_AUTHENTICATION_FAILURE,
                code="invalid_login",
            )
