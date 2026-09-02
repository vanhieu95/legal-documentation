from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext

from apps.accounts.policies import ApplicationPermission, application_permission_required


@application_permission_required(ApplicationPermission.VIEW_CASES)
def case_list_placeholder(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "placeholders/domain.html",
        {
            "page_title": gettext("Cases"),
            "state_message": gettext("Case management is not available yet."),
        },
    )
