from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext

from apps.accounts.policies import ApplicationPermission, application_permission_required


@application_permission_required(ApplicationPermission.VIEW_TEMPLATES)
def template_list_placeholder(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "placeholders/domain.html",
        {
            "page_title": gettext("Templates"),
            "state_message": gettext("Template management is not available yet."),
        },
    )
