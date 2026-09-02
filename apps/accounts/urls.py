from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("session-expired/", views.session_expired, name="session-expired"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
