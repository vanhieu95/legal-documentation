from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied
from django.db import connection, models
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import seed_administrator_permissions
from apps.cases.models import CaseRecord
from apps.cases.policies import case_object_policy
from apps.documents.dashboard import (
    DASHBOARD_GENERATION_LIMIT,
    MVP_DOCUMENT_TYPE_CODES,
    document_dashboard_summary,
)
from apps.documents.models import GeneratedDocument, TemplateVersion
from apps.documents.tests.test_template_versions import template_values
from tests.factories import CaseRecordFactory

pytestmark = pytest.mark.django_db


def _actor(user_factory: object) -> User:
    actor = cast(Callable[..., User], user_factory)(username="document-dashboard-admin")
    actor.groups.add(seed_administrator_permissions())
    return actor


def _attempt(
    *,
    actor: User,
    case: CaseRecord,
    template: TemplateVersion,
    index: int,
    status: GeneratedDocument.Status,
) -> GeneratedDocument:
    attempt = GeneratedDocument.objects.create(
        case=case,
        type_key="synthetic-platform-test",
        template_version=template,
        schema_version="v1",
        source_draft_id=case.pk,
        case_revision=case.revision,
        draft_revision=1,
        input_snapshot={"version": 1, "values": {"title": "Synthetic"}},
        resolved_values_snapshot={"version": 1, "values": {"title": "Synthetic"}},
        override_snapshot={"version": 1, "values": {}},
        template_snapshot={
            "version": 1,
            "identity": {
                "id": str(template.pk),
                "type_key": template.type_key,
                "version": template.version,
                "checksum_sha256": template.checksum_sha256,
            },
        },
        actor=actor,
        idempotency_key_hash=f"{index:064x}",
    )
    occurred_at = timezone.now() + timedelta(minutes=index)
    values: dict[str, object]
    if status == GeneratedDocument.Status.GENERATED:
        values = {
            "status": status,
            "generated_at": occurred_at,
            "output_storage_key": f"generated/{case.pk}/{attempt.pk}/synthetic-{index}.docx",
            "output_filename": f"synthetic-{index}.docx",
            "output_size": 12,
            "output_checksum_sha256": "c" * 64,
        }
    elif status == GeneratedDocument.Status.FAILED:
        values = {
            "status": status,
            "failed_at": occurred_at,
            "failure_category": GeneratedDocument.FailureCategory.RENDER_ERROR,
            "failure_correlation_id": f"dashboard-{index}",
        }
    else:
        return attempt
    models.QuerySet.update(GeneratedDocument.objects.filter(pk=attempt.pk), **values)
    return GeneratedDocument.objects.get(pk=attempt.pk)


def test_document_dashboard_reports_positive_production_coverage_and_excludes_synthetic_type(
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor(user_factory)
    template = TemplateVersion.objects.create(**template_values(uploader=actor))
    template.validation_report = {
        "schema_version": 1,
        "result": "valid",
        "categories": [],
        "counts": {"synthetic_renders": 2},
    }
    template.save(update_fields=("validation_report",))
    template.transition_to(TemplateVersion.Status.VALID)
    template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)

    production_registration = SimpleNamespace(
        official_code="01-VDS",
        vietnamese_name="Synthetic production registration",
    )
    production_registry = SimpleNamespace(
        describe=lambda: (
            {
                "key": "vds-01",
                "enabled": True,
                "is_synthetic": False,
            },
        ),
        get=lambda key: production_registration,
    )
    monkeypatch.setattr("apps.documents.models.document_registry", production_registry)
    monkeypatch.setattr("apps.documents.dashboard.document_registry", production_registry)
    production_template = TemplateVersion.objects.create(
        **template_values(
            uploader=actor,
            type_key="vds-01",
            version="v1.0-production",
            original_filename="vds-01.docx",
        )
    )
    production_template.validation_report = {
        "schema_version": 1,
        "result": "valid",
        "categories": [],
        "counts": {"synthetic_renders": 2},
    }
    production_template.save(update_fields=("validation_report",))
    production_template.transition_to(TemplateVersion.Status.VALID)
    production_template.transition_to(TemplateVersion.Status.ACTIVE, actor=actor)

    summary = document_dashboard_summary(actor=actor)

    assert summary.template_total == 12
    assert summary.active_template_count == 1
    assert tuple(item.official_code for item in summary.template_coverage) == (
        "01-VDS",
        "03-VDS",
        "10-VDS",
        "05-VDS",
        "09-VDS",
        "15-VDS",
        "21-VDS",
        "31-VDS",
        "22-VDS",
        "11-VDS",
        "04-VDS",
        "12-VDS",
    )
    assert tuple(item.type_key for item in summary.template_coverage) == tuple(
        key for key, _code in MVP_DOCUMENT_TYPE_CODES
    )
    assert summary.template_coverage[0].is_deployed
    assert summary.template_coverage[0].has_active_template
    assert summary.template_coverage[0].upload_url == reverse(
        "documents:template-upload", args=["vds-01"]
    )
    assert all(
        not item.is_deployed and not item.has_active_template
        for item in summary.template_coverage[1:]
    )


def test_document_dashboard_returns_bounded_safe_attempts_and_canonical_history_links(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    template = TemplateVersion.objects.create(**template_values(uploader=actor))
    cases = [
        cast(
            CaseRecord,
            CaseRecordFactory(
                internal_reference=f"SYN-DASH-DOC-{index:02d}",
                created_by=actor,
                last_edited_by=actor,
            ),
        )
        for index in range(DASHBOARD_GENERATION_LIMIT + 2)
    ]
    attempts = [
        _attempt(
            actor=actor,
            case=case,
            template=template,
            index=index + 1,
            status=(
                GeneratedDocument.Status.FAILED if index % 2 else GeneratedDocument.Status.GENERATED
            ),
        )
        for index, case in enumerate(cases)
    ]

    summary = document_dashboard_summary(actor=actor)

    assert len(summary.recent_attempts) == DASHBOARD_GENERATION_LIMIT
    assert [item.id for item in summary.recent_attempts] == [
        attempt.pk for attempt in reversed(attempts[-DASHBOARD_GENERATION_LIMIT:])
    ]
    assert summary.failed_total == 3
    assert summary.failed_attention_url == reverse(
        "documents:case-generation-history", args=[attempts[5].case_id]
    )
    assert [item.id for item in summary.failed_attempts] == [
        attempts[index].pk for index in (5, 3, 1)
    ]
    for item in (*summary.recent_attempts, *summary.failed_attempts):
        assert item.history_url == reverse("documents:case-generation-history", args=[item.case_id])
        assert not hasattr(item, "output_filename")
        assert not hasattr(item, "failure_correlation_id")
        assert not hasattr(item, "storage_key")


def test_document_dashboard_applies_case_scope_and_requires_document_permissions(
    user_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor(user_factory)
    template = TemplateVersion.objects.create(**template_values(uploader=actor))
    visible = cast(
        CaseRecord,
        CaseRecordFactory(
            internal_reference="SYN-DASH-DOC-VISIBLE",
            created_by=actor,
            last_edited_by=actor,
        ),
    )
    excluded = cast(
        CaseRecord,
        CaseRecordFactory(
            internal_reference="SYN-DASH-DOC-EXCLUDED",
            created_by=actor,
            last_edited_by=actor,
        ),
    )
    _attempt(
        actor=actor,
        case=visible,
        template=template,
        index=1,
        status=GeneratedDocument.Status.GENERATED,
    )
    _attempt(
        actor=actor,
        case=excluded,
        template=template,
        index=2,
        status=GeneratedDocument.Status.FAILED,
    )
    monkeypatch.setattr(
        case_object_policy,
        "scope_queryset",
        lambda scoped_actor, queryset: queryset.exclude(pk=excluded.pk),
    )

    summary = document_dashboard_summary(actor=actor)

    assert [item.case_id for item in summary.recent_attempts] == [visible.pk]
    assert summary.failed_total == 0
    assert summary.failed_attention_url is None

    group = actor.groups.get(name="Administrator")
    group.permissions.remove(Permission.objects.get(codename="view_document_history"))
    actor = User.objects.get(pk=actor.pk)
    with pytest.raises(PermissionDenied):
        document_dashboard_summary(actor=actor)


def test_document_dashboard_query_count_does_not_grow_with_attempt_rows(
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    template = TemplateVersion.objects.create(**template_values(uploader=actor))
    for index in range(DASHBOARD_GENERATION_LIMIT + 3):
        case = cast(
            CaseRecord,
            CaseRecordFactory(
                internal_reference=f"SYN-DASH-DOC-BUDGET-{index:02d}",
                created_by=actor,
                last_edited_by=actor,
            ),
        )
        _attempt(
            actor=actor,
            case=case,
            template=template,
            index=index + 1,
            status=(
                GeneratedDocument.Status.FAILED if index % 2 else GeneratedDocument.Status.GENERATED
            ),
        )

    with CaptureQueriesContext(connection) as queries:
        summary = document_dashboard_summary(actor=actor)
        rendered = [
            (item.case_reference, item.type_code, item.status, item.occurred_at, item.history_url)
            for item in (*summary.recent_attempts, *summary.failed_attempts)
        ]

    assert rendered
    generation_queries = [
        query for query in queries if GeneratedDocument._meta.db_table in query["sql"]
    ]
    assert len(generation_queries) == 3, [query["sql"] for query in queries]
    assert len(queries) <= 9, [query["sql"] for query in queries]


def test_dashboard_renders_safe_recent_and_failed_history_links(
    client: Client,
    user_factory: object,
) -> None:
    actor = _actor(user_factory)
    template = TemplateVersion.objects.create(**template_values(uploader=actor))
    generated_case = cast(
        CaseRecord,
        CaseRecordFactory(
            internal_reference="SYN-DASH-DOC-GENERATED",
            created_by=actor,
            last_edited_by=actor,
        ),
    )
    failed_case = cast(
        CaseRecord,
        CaseRecordFactory(
            internal_reference="SYN-DASH-DOC-FAILED",
            created_by=actor,
            last_edited_by=actor,
        ),
    )
    generated = _attempt(
        actor=actor,
        case=generated_case,
        template=template,
        index=1,
        status=GeneratedDocument.Status.GENERATED,
    )
    failed = _attempt(
        actor=actor,
        case=failed_case,
        template=template,
        index=2,
        status=GeneratedDocument.Status.FAILED,
    )
    client.force_login(actor)

    response = client.get(reverse("accounts:dashboard"))

    html = response.content.decode()
    assert response.status_code == 200
    assert generated_case.internal_reference in html
    assert failed_case.internal_reference in html
    assert reverse("documents:case-generation-history", args=[generated_case.pk]) in html
    assert reverse("documents:case-generation-history", args=[failed_case.pk]) in html
    assert f'href="{reverse("documents:case-generation-history", args=[failed_case.pk])}"' in html
    assert generated.output_filename not in html
    assert failed.failure_correlation_id not in html
    assert generated.output_storage_key not in html
