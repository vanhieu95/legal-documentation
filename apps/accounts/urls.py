from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
