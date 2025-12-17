from django.urls import path
from . import views

urlpatterns = [
    path("", views.session_list, name="session_list"),
    path("create/", views.session_create, name="session_create"),
    path("<int:session_id>/", views.session_detail, name="session_detail"),
    path("<int:session_id>/join/", views.join_session, name="join_session"),
]
