from django.urls import path

from apps.cases import views

app_name = "cases"

urlpatterns = [path("cases/", views.case_list_placeholder, name="list")]
