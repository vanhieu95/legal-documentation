from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import cast

import pytest
from django.contrib.auth.models import User

from apps.accounts.permissions import seed_administrator_permissions
from apps.cases.document_prefill import authorize_document_case, document_case_transfer
from apps.cases.models import CaseRecord
from apps.documents.prefill import PrefillSource, map_case_transfer
from apps.documents.registry import document_registry
from tests.factories import CaseRecordFactory

pytestmark = pytest.mark.django_db


def test_explicit_mapping_provides_initial_values_sources_and_override_comparison(
    user_factory: Callable[..., User],
) -> None:
    actor = user_factory(username="synthetic-mapping-admin")
    actor.groups.add(seed_administrator_permissions())
    case = cast(
        CaseRecord,
        CaseRecordFactory(
            created_by=actor,
            last_edited_by=actor,
            matter_type="Yêu cầu xác định sự kiện pháp lý",
        ),
    )
    transfer = document_case_transfer(authorize_document_case(actor=actor, case_id=case.pk))
    registration = document_registry.get("synthetic-platform-test")

    prefill = map_case_transfer(
        registration=registration,
        transfer=transfer,
        draft_payload={"title": "Ghi đè riêng", "notes": "Nội dung riêng"},
    )

    assert prefill.form_initial == MappingProxyType(
        {"title": "Ghi đè riêng", "notes": "Nội dung riêng"}
    )
    assert prefill.formset_initial == MappingProxyType({})
    assert prefill.sources["title"].source is PrefillSource.CASE_MATTER
    assert prefill.sources["notes"].source is PrefillSource.DOCUMENT
    assert prefill.overrides["title"].case_value == "Yêu cầu xác định sự kiện pháp lý"
    assert prefill.overrides["title"].draft_value == "Ghi đè riêng"
    with pytest.raises(TypeError):
        prefill.form_initial["title"] = "mutated"  # type: ignore[index]


def test_mapping_does_not_mutate_case_or_call_case_write_services(
    user_factory: Callable[..., User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = user_factory(username="synthetic-mapping-write-guard")
    actor.groups.add(seed_administrator_permissions())
    case = cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))
    transfer = document_case_transfer(authorize_document_case(actor=actor, case_id=case.pk))
    before = (case.matter_type, case.revision, case.updated_at)

    def forbidden_write(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("case write service called")

    monkeypatch.setattr("apps.cases.services.update_case", forbidden_write)
    mapped = map_case_transfer(
        registration=document_registry.get("synthetic-platform-test"),
        transfer=transfer,
        draft_payload={"title": "Draft-only override"},
    )

    assert mapped.form_initial["title"] == "Draft-only override"
    case.refresh_from_db()
    assert (case.matter_type, case.revision, case.updated_at) == before


def test_mapping_is_explicit_and_rejects_unknown_contracts(
    user_factory: Callable[..., User],
) -> None:
    actor = user_factory(username="synthetic-explicit-mapping")
    actor.groups.add(seed_administrator_permissions())
    case = cast(CaseRecord, CaseRecordFactory(created_by=actor, last_edited_by=actor))
    transfer = document_case_transfer(authorize_document_case(actor=actor, case_id=case.pk))
    registration = document_registry.get("synthetic-platform-test")
    from dataclasses import replace

    with pytest.raises(LookupError):
        map_case_transfer(
            registration=replace(registration, key="synthetic-unknown"),
            transfer=transfer,
            draft_payload={},
        )
