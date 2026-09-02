from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

ADMINISTRATOR_GROUP_NAME = "Administrator"

APPLICATION_PERMISSION_DEFINITIONS = (
    ("view_cases", "Can view cases"),
    ("add_cases", "Can add cases"),
    ("change_cases", "Can change cases"),
    ("archive_cases", "Can archive cases"),
    ("restore_cases", "Can restore cases"),
    ("view_reference_entities", "Can view reference entities"),
    ("add_reference_entities", "Can add reference entities"),
    ("change_reference_entities", "Can change reference entities"),
    ("deactivate_reference_entities", "Can deactivate reference entities"),
    ("view_document_drafts", "Can view document drafts"),
    ("add_document_drafts", "Can add document drafts"),
    ("change_document_drafts", "Can change document drafts"),
    ("generate_documents", "Can generate documents"),
    ("view_document_history", "Can view document history"),
    ("download_documents", "Can download documents"),
    ("view_templates", "Can view templates"),
    ("upload_templates", "Can upload templates"),
    ("validate_templates", "Can validate templates"),
    ("activate_templates", "Can activate templates"),
    ("deactivate_templates", "Can deactivate templates"),
    ("view_audit", "Can view audit events"),
)
APPLICATION_PERMISSION_CODENAMES = tuple(
    codename for codename, _name in APPLICATION_PERMISSION_DEFINITIONS
)


@transaction.atomic
def seed_administrator_permissions() -> Group:
    """Create the central role and make its application permissions deterministic."""
    from apps.accounts.models import ApplicationAccess

    content_type = ContentType.objects.get_for_model(ApplicationAccess, for_concrete_model=False)
    permissions = [
        Permission.objects.update_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )[0]
        for codename, name in APPLICATION_PERMISSION_DEFINITIONS
    ]
    administrator_group, _created = Group.objects.get_or_create(name=ADMINISTRATOR_GROUP_NAME)
    administrator_group.permissions.set(permissions)
    return administrator_group
