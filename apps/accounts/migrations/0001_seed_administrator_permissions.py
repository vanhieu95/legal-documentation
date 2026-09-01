from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

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


def seed_permissions(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    database_alias = schema_editor.connection.alias

    content_type, _created = ContentType.objects.using(database_alias).get_or_create(
        app_label="accounts",
        model="applicationaccess",
    )
    permissions = [
        Permission.objects.using(database_alias).update_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )[0]
        for codename, name in APPLICATION_PERMISSION_DEFINITIONS
    ]
    administrator_group, _created = Group.objects.using(database_alias).get_or_create(
        name=ADMINISTRATOR_GROUP_NAME
    )
    administrator_group.permissions.set(permissions)


def unseed_permissions(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    database_alias = schema_editor.connection.alias

    content_type = (
        ContentType.objects.using(database_alias)
        .filter(
            app_label="accounts",
            model="applicationaccess",
        )
        .first()
    )
    if content_type is None:
        return

    permissions = Permission.objects.using(database_alias).filter(
        content_type=content_type,
        codename__in=[codename for codename, _name in APPLICATION_PERMISSION_DEFINITIONS],
    )
    administrator_group = (
        Group.objects.using(database_alias).filter(name=ADMINISTRATOR_GROUP_NAME).first()
    )
    if administrator_group is not None:
        administrator_group.permissions.remove(*permissions)
        if not administrator_group.user_set.exists():
            administrator_group.delete()
    permissions.delete()
    content_type.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApplicationAccess",
            fields=[],
            options={
                "proxy": True,
                "indexes": [],
                "constraints": [],
                "default_permissions": (),
                "permissions": APPLICATION_PERMISSION_DEFINITIONS,
            },
            bases=("auth.user",),
        ),
        migrations.RunPython(seed_permissions, unseed_permissions),
    ]
