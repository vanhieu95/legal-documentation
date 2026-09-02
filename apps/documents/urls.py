from django.urls import path

from apps.documents import views

app_name = "documents"

urlpatterns = [path("templates/", views.template_list_placeholder, name="templates")]
