"""Create deterministic synthetic principals for the local browser-test database."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.browser_test")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from django.contrib.sessions.models import Session  # noqa: E402

from apps.accounts.permissions import seed_administrator_permissions  # noqa: E402
from apps.cases.models import Court, Entity, Official  # noqa: E402
from apps.documents.models import TemplateVersion  # noqa: E402

if settings.SETTINGS_MODULE != "config.settings.browser_test":
    raise RuntimeError("Browser fixtures may only be created with browser-test settings.")

administrator_group = seed_administrator_permissions()
Session.objects.all().delete()


def replace_synthetic_user(
    username: str,
    password: str,
    *,
    is_superuser: bool = False,
    is_staff: bool = False,
) -> User:
    user, _created = User.objects.get_or_create(username=username)
    user.is_active = True
    user.is_superuser = is_superuser
    user.is_staff = is_staff
    user.set_password(password)
    user.save()
    user.groups.clear()
    return user


administrator = replace_synthetic_user(
    "synthetic-browser-administrator",
    "synthetic-browser-password-123!",
)
administrator.groups.add(administrator_group)

for _index in range(2):
    confirmation_template = TemplateVersion.objects.create(
        type_key="synthetic-platform-test",
        version=f"browser-confirm-{uuid.uuid4().hex[:12]}",
        original_filename="synthetic-browser-template.docx",
        checksum_sha256="d" * 64,
        byte_size=128,
        uploader=administrator,
        approval_reference="SYNTHETIC-BROWSER-APPROVAL",
    )
    confirmation_template.validation_report = {
        "schema_version": 1,
        "result": "valid",
        "categories": [],
        "counts": {"synthetic_renders": 2},
    }
    confirmation_template.save(update_fields=("validation_report",))
    confirmation_template.transition_to(TemplateVersion.Status.VALID)

if not TemplateVersion.objects.filter(
    type_key="synthetic-platform-test", status=TemplateVersion.Status.ACTIVE
).exists():
    active_template = TemplateVersion.objects.filter(
        type_key="synthetic-platform-test", status=TemplateVersion.Status.VALID
    ).first()
    if active_template is not None:
        active_template.transition_to(TemplateVersion.Status.ACTIVE, actor=administrator)

replace_synthetic_user(
    "synthetic-browser-superuser",
    "synthetic-browser-password-123!",
    is_superuser=True,
    is_staff=True,
)

replace_synthetic_user(
    "synthetic-browser-non-administrator",
    "synthetic-browser-password-123!",
)

court, _created = Court.objects.update_or_create(
    code="SYN-BROWSER",
    defaults={
        "full_name": "Tòa án nhân dân thử nghiệm trình duyệt",
        "short_name": "TAND thử nghiệm",
        "level": Court.Level.DISTRICT,
        "address": "Địa chỉ hành chính thử nghiệm",
        "is_active": True,
    },
)

participant_entity, _created = Entity.objects.update_or_create(
    identity_document_number="SYN-BROWSER-PARTICIPANT-ID",
    defaults={
        "kind": Entity.Kind.INDIVIDUAL,
        "legal_name": "Người tham gia thử nghiệm trình duyệt",
        "display_name": "Người tham gia thử nghiệm",
        "is_active": True,
    },
)
official_entity, _created = Entity.objects.update_or_create(
    identity_document_number="SYN-BROWSER-OFFICIAL-ID",
    defaults={
        "kind": Entity.Kind.INDIVIDUAL,
        "legal_name": "Cán bộ thử nghiệm trình duyệt",
        "display_name": "Cán bộ thử nghiệm",
        "is_active": True,
    },
)
Official.objects.update_or_create(
    entity=official_entity,
    defaults={
        "home_court": court,
        "title": "Thẩm phán thử nghiệm",
        "position": "Bộ phận dân sự thử nghiệm",
        "is_active": True,
    },
)
