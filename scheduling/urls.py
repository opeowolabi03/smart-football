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

    path("<int:session_id>/team-allocation/", views.team_allocation, name="team_allocation"),
    path("<int:session_id>/generate-teams/", views.generate_teams, name="generate_teams"),
    path("<int:session_id>/cancel-allocation/", views.cancel_team_allocation, name="cancel_team_allocation"),
    path("<int:session_id>/confirm-allocation/", views.confirm_team_allocation, name="confirm_team_allocation"),

    path("<int:session_id>/rate/", views.rate_session, name="rate_session"),
    path("<int:session_id>/attendance/", views.attendance_management, name="attendance_management"),
    path("<int:session_id>/attendance/<int:participation_id>/<str:status>/", views.set_attendance_status, name="set_attendance_status"),
    path("<int:session_id>/attendance/bulk/", views.bulk_attendance_action, name="bulk_attendance_action"),
    path("<int:session_id>/results/", views.match_results, name="match_results"),
    path("<int:session_id>/results/edit/", views.edit_match_result, name="edit_match_result"),
]