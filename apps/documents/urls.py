from django.urls import path

from apps.documents import views

app_name = "documents"

urlpatterns = [
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
