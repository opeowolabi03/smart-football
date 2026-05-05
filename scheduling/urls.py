from django.urls import path
from . import views

urlpatterns = [
    path("", views.player_dashboard, name="player_dashboard"),
    path("sessions/", views.session_list, name="session_list"),
    path("create/", views.session_create, name="session_create"),
    path("organiser/", views.organiser_dashboard, name="organiser_dashboard"),

    path("<int:session_id>/", views.session_detail, name="session_detail"),
    path("<int:session_id>/join/", views.join_session, name="join_session"),
    path("<int:session_id>/leave/", views.leave_session, name="leave_session"),
    path("<int:session_id>/toggle-attendance/<int:participation_id>/", views.toggle_attendance, name="toggle_attendance"),
    path("<int:session_id>/rate/", views.rate_session, name="rate_session"),
    path("<int:session_id>/teams/", views.view_teams, name="view_teams"),
    path("<int:session_id>/generate-teams/", views.generate_teams, name="generate_teams"),

]