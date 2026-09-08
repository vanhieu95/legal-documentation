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
