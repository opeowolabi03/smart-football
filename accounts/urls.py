from django.urls import path
from django.contrib.auth import views as auth_views

from . import views


urlpatterns = [
    path("login/", views.auth_page, {"mode": "login"}, name="login"),
    path("signup/", views.auth_page, {"mode": "signup"}, name="signup"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", views.edit_profile, name="edit_profile"),
]