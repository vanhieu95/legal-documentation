from __future__ import annotations

from collections.abc import Callable

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse

from apps.accounts.permissions import ADMINISTRATOR_GROUP_NAME
from apps.audit.models import AuditEvent
from apps.cases.models import CaseRecord

SECTIONS = ("overview", "participants", "representatives", "assignments", "hearings")


@pytest.fixture
def administrator(user_factory: Callable[..., User]) -> User:
    user = user_factory(username="synthetic-case-section-admin")
    user.groups.add(Group.objects.get(name=ADMINISTRATOR_GROUP_NAME))
    return user


def section_url(case: CaseRecord, section: str) -> str:
    return f"{reverse('cases:detail', kwargs={'case_id': case.pk})}?section={section}"


@pytest.mark.django_db
@pytest.mark.parametrize("section", SECTIONS)
def test_every_case_detail_section_has_full_and_htmx_rendering(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
    section: str,
) -> None:
    case = case_factory(internal_reference="SYN-SECTION-001")
    client.force_login(administrator)

    full = client.get(section_url(case, section))
    fragment = client.get(section_url(case, section), HTTP_HX_REQUEST="true")

    assert full.status_code == 200
    assert "cases/detail.html" in [template.name for template in full.templates]
    assert "<html" in full.content.decode()
    assert fragment.status_code == 200
    assert "cases/_case_section.html" in [template.name for template in fragment.templates]
    assert "<html" not in fragment.content.decode()
    assert full.context["section"] == section
    assert fragment.context["section"] == section
    assert f"section={section}" in full.content.decode()
    assert "HX-Request" in full.headers["Vary"]
    assert "HX-Request" in fragment.headers["Vary"]


@pytest.mark.django_db
def test_case_section_gets_are_side_effect_free_and_use_ordinary_links(
    client: Client,
    administrator: User,
    case_factory: Callable[..., CaseRecord],
) -> None:
    case = case_factory()
    client.force_login(administrator)

    response = client.get(section_url(case, "participants"))

    html = response.content.decode()
    assert response.status_code == 200
    for section in SECTIONS:
        assert f'href="{section_url(case, section)}"' in html
    assert AuditEvent.objects.count() == 0
