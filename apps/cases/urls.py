from django.urls import path

from apps.cases import views

app_name = "cases"

urlpatterns = [
    path("cases/", views.case_list, name="list"),
    path("cases/new/", views.case_create, name="create"),
    path("cases/<uuid:case_id>/", views.case_detail, name="detail"),
    path("cases/<uuid:case_id>/edit/", views.case_edit, name="edit"),
    path("cases/<uuid:case_id>/archive/", views.case_archive, name="archive"),
    path("cases/<uuid:case_id>/restore/", views.case_restore, name="restore"),
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
