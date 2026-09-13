from django.urls import path

from apps.documents import views, workflow_views

app_name = "documents"

urlpatterns = [
    path(
        "cases/<uuid:case_id>/documents/",
        workflow_views.case_document_selector,
        name="case-document-selector",
    ),
    path(
        "cases/<uuid:case_id>/documents/<slug:type_key>/",
        workflow_views.case_document_draft,
        name="case-document-draft",
    ),
    path("templates/", views.template_list, name="template-list"),
    path("templates/", views.template_list, name="templates"),
    path(
        "templates/<slug:type_key>/upload/",
        views.template_upload,
        name="template-upload",
    ),
    path(
        "templates/<slug:type_key>/<uuid:template_id>/activate/",
        views.template_activate,
        name="template-activate",
    ),
    path(
        "templates/<slug:type_key>/<uuid:template_id>/deactivate/",
        views.template_deactivate,
        name="template-deactivate",
    ),
]
