from __future__ import annotations

from django.contrib.auth.models import User
from django.db.models import Model, QuerySet

from apps.cases.models import CaseRecord


class ReferenceObjectPolicy[TModel: Model]:
    """MVP organization-wide scope with an explicit future object-policy boundary."""

    def scope_queryset(self, actor: User, queryset: QuerySet[TModel]) -> QuerySet[TModel]:
        return queryset


reference_object_policy = ReferenceObjectPolicy[Model]()
case_object_policy = ReferenceObjectPolicy[CaseRecord]()


def can_edit_case(case: CaseRecord) -> bool:
    """Return whether the case lifecycle permits mutation."""
    return case.status == CaseRecord.Status.ACTIVE


def can_generate_documents_for_case(case: CaseRecord) -> bool:
    """Stable domain predicate for later document-generation authorization."""
    return case.status == CaseRecord.Status.ACTIVE
