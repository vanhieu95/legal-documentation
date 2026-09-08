from django.urls import path

from apps.cases import views

app_name = "cases"

urlpatterns = [
    path("cases/", views.case_list_placeholder, name="list"),
    path("cases/new/", views.case_create, name="create"),
    path("cases/<uuid:case_id>/", views.case_detail, name="detail"),
    path(
        "case-references/<str:reference_type>/",
        views.reference_list,
        name="reference-list",
    ),
    path(
        "case-references/<str:reference_type>/new/",
        views.reference_create,
        name="reference-create",
    ),
    path(
        "case-references/<str:reference_type>/<uuid:object_id>/edit/",
        views.reference_edit,
        name="reference-edit",
    ),
    path(
        "case-references/<str:reference_type>/<uuid:object_id>/deactivate/",
        views.reference_deactivate,
        name="reference-deactivate",
    ),
]
