from django.contrib.auth.models import User

from apps.accounts.permissions import APPLICATION_PERMISSION_DEFINITIONS


class ApplicationAccess(User):
    """A table-free anchor for the application's custom permission contract."""

    class Meta:
        proxy = True
        default_permissions = ()
        permissions = APPLICATION_PERMISSION_DEFINITIONS
