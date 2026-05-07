from datetime import datetime
from math import ceil

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .ml_team_allocator import (
    allocate_teams_ml,
    calculate_player_strength,
    peer_rating_score,
    attendance_reliability_score,
)

from .forms import RatingForm
from .models import (
    MatchSession,
    Participation,
    Rating,
    TeamAssignment,
    MatchResult,
    PlayerMatchStat,
)


def _is_organiser_user(user):
    if not user.is_authenticated:
        return False

    if user.is_staff:
        return True

    try:
        return str(user.profile.role).lower() == "organiser"
    except Exception:
        return False


def player_strength(user):
    profile = getattr(user, "profile", None)

    if not profile:
        return 0.0

    return (
        (getattr(profile, "skill_level", 0) * 1.0)
        + (getattr(profile, "fitness_level", 0) * 0.7)
        + (getattr(profile, "overall_rating", 0) * 2.0)
        + (getattr(profile, "reliability_score", 0) * 2.0)
    )


def _stars_from_five(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0

    value = max(0, min(value, 5))
    return "★" * value + "☆" * (5 - value)


def _display_choice(obj, field_name, default="Not set"):
    if obj is None:
        return default

    display_method = getattr(obj, f"get_{field_name}_display", None)

    if callable(display_method):
        return display_method()

    value = getattr(obj, field_name, default)

    label_map = {
        "any": "Any",
        "ANY": "Any",
        "GK": "Goalkeeper",
        "gk": "Goalkeeper",
        "DEF": "Defender",
        "def": "Defender",
        "MID": "Midfielder",
        "mid": "Midfielder",
        "FWD": "Forward",
        "fwd": "Forward",
        "beginner": "Beginner",
        "intermediate": "Intermediate",
        "advanced": "Advanced",
        "player": "Player",
        "organiser": "Organiser",
    }

    return label_map.get(str(value), str(value).replace("_", " ").title())


def _session_format(session):
    title = session.title.lower()

    if "training" in title:
        return "Training"

    if "futsal" in title:
        return "Futsal"

    return "5-a-side"


def _session_status(session):
    if session.start_datetime < timezone.now():
        return "Completed"

    return "Upcoming"


def _get_user_profile(user):
    """
    Safely gets a user's profile.
    This avoids crashes if a profile is missing.
    """
    try:
        return user.profile
    except Exception:
        return None


def _clamp_number(value, minimum, maximum, default=0):
    """
    Keeps numbers inside a safe range.
    Example: skill cannot go below 1 or above 5.
    """
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = default

    return max(minimum, min(value, maximum))


def _experience_score(profile):
    """
    Converts experience text into a 1-5 score.
    """
    if not profile:
        return 1.0

    experience_value = str(getattr(profile, "experience", "")).lower()

    experience_scores = {
        "beginner": 1.0,
        "intermediate": 3.0,
        "advanced": 5.0,
    }

    return experience_scores.get(experience_value, 1.0)


def _peer_rating_score(user):
    """
    Gets the average peer rating received by this player.
    If they have no ratings yet, use 3/5 as a neutral default.
    """
    average_rating = Rating.objects.filter(ratee=user).aggregate(
        average=Avg("score")
    )["average"]

    if average_rating is None:
        return 3.0

    return _clamp_number(average_rating, 1, 5, default=3)


def _reliability_score(user):
    """
    Uses attendance reliability as part of team balancing.
    If profile.reliability_score exists, it should be 0.0 to 1.0.
    This converts it to a 1-5 score.
    """
    profile = _get_user_profile(user)

    if not profile:
        return 3.0

    reliability = getattr(profile, "reliability_score", None)

    if reliability is None:
        return 3.0

    reliability = _clamp_number(reliability, 0, 1, default=0.5)

    return max(1.0, reliability * 5)

def _profile_score(user):
    return calculate_player_strength(user)

def _team_fairness_score(team_a_total, team_b_total):
    """
    Returns a fairness score out of 100.
    A smaller difference between teams means a higher fairness score.
    """
    highest_total = max(team_a_total, team_b_total)

    if highest_total <= 0:
        return 0

    difference = abs(team_a_total - team_b_total)

    fairness = 100 - ((difference / highest_total) * 100)

    return round(max(0, fairness))


def _fairness_label(score):
    if score >= 90:
        return "Excellent"

    if score >= 75:
        return "Good"

    if score >= 60:
        return "Fair"

    return "Needs review"

def _attendance_percentage(count, total):
    if total <= 0:
        return 0

    return round((count / total) * 100)


class MatchSessionForm(forms.ModelForm):
    start_date = forms.DateField(
        label="Date",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "class": "form-input",
                "type": "date",
            },
        ),
    )

    start_time = forms.TimeField(
        label="Start Time",
        input_formats=["%H:%M"],
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={
                "class": "form-input",
                "type": "time",
            },
        ),
    )

    class Meta:
        model = MatchSession
        fields = ["title", "location", "capacity"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. Friday Night 5-a-side",
            }),
            "location": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. Sports Hall 1, Astro Pitch, Local Park",
            }),
            "capacity": forms.NumberInput(attrs={
                "class": "form-input",
                "min": "2",
                "max": "30",
                "placeholder": "10",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk and self.instance.start_datetime:
            local_datetime = timezone.localtime(self.instance.start_datetime)
            self.fields["start_date"].initial = local_datetime.date()
            self.fields["start_time"].initial = local_datetime.strftime("%H:%M")

    def clean_capacity(self):
        capacity = self.cleaned_data.get("capacity")

        if capacity is None:
            return capacity

        if capacity < 2:
            raise forms.ValidationError("Capacity must be at least 2 players.")

        if capacity > 30:
            raise forms.ValidationError("Capacity cannot be more than 30 players for this prototype.")

        return capacity

    def save(self, commit=True):
        session = super().save(commit=False)

        start_date = self.cleaned_data["start_date"]
        start_time = self.cleaned_data["start_time"]

        combined_datetime = datetime.combine(start_date, start_time)

        if timezone.is_naive(combined_datetime):
            combined_datetime = timezone.make_aware(
                combined_datetime,
                timezone.get_current_timezone(),
            )

        session.start_datetime = combined_datetime

        if commit:
            session.save()

        return session


@login_required
def player_dashboard(request):
    user = request.user

    try:
        profile = user.profile
    except ObjectDoesNotExist:
        profile = None

    display_name = user.get_full_name().strip() or user.username

    participations = Participation.objects.filter(user=user).select_related("session")
    matches_joined = participations.count()
    attended_count = participations.filter(attended=True).count()

    if matches_joined > 0:
        attendance_rate = round((attended_count / matches_joined) * 100)
    else:
        attendance_rate = 0

    rating_stats = Rating.objects.filter(ratee=user).aggregate(
        average_rating=Avg("score"),
        rating_count=Count("id"),
    )

    average_rating = rating_stats["average_rating"]
    rating_count = rating_stats["rating_count"]

    if average_rating is not None:
        average_rating = round(average_rating, 1)

    teams_generated = (
        TeamAssignment.objects
        .filter(user=user)
        .values("session")
        .distinct()
        .count()
    )

    upcoming_sessions = list(
        MatchSession.objects
        .filter(start_datetime__gte=timezone.now())
        .annotate(participant_count=Count("participants"))
        .order_by("start_datetime")[:4]
    )

    user_participations = Participation.objects.filter(
        user=user,
        session__in=upcoming_sessions,
    )

    joined_session_ids = {
        participation.session_id
        for participation in user_participations
    }

    team_assignments = TeamAssignment.objects.filter(
        user=user,
        session__in=upcoming_sessions,
    )

    team_map = {
        assignment.session_id: assignment.team
        for assignment in team_assignments
    }

    session_cards = []

    for session in upcoming_sessions:
        session_cards.append({
            "session": session,
            "is_joined": session.id in joined_session_ids,
            "team": team_map.get(session.id),
            "is_full": session.participant_count >= session.capacity,
            "spaces_left": max(session.capacity - session.participant_count, 0),
        })

    profile_summary = {
        "name": display_name,
        "role": _display_choice(profile, "role", "Player"),
        "skill_level": getattr(profile, "skill_level", 0) if profile else 0,
        "fitness_level": getattr(profile, "fitness_level", 0) if profile else 0,
        "skill_stars": _stars_from_five(getattr(profile, "skill_level", 0) if profile else 0),
        "fitness_stars": _stars_from_five(getattr(profile, "fitness_level", 0) if profile else 0),
        "position": _display_choice(profile, "position_preference"),
        "experience": _display_choice(profile, "experience"),
    }

    is_organiser = _is_organiser_user(user)

    return render(request, "scheduling/player_dashboard.html", {
        "display_name": display_name,
        "matches_joined": matches_joined,
        "attended_count": attended_count,
        "attendance_rate": attendance_rate,
        "average_rating": average_rating,
        "rating_count": rating_count,
        "teams_generated": teams_generated,
        "session_cards": session_cards,
        "profile_summary": profile_summary,
        "is_organiser": is_organiser,
    })


def session_list(request):
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")
    format_filter = request.GET.get("format", "all")
    sort = request.GET.get("sort", "newest")
    mine_filter = request.GET.get("mine") == "1"

    base_sessions = MatchSession.objects.all()

    all_sessions_count = base_sessions.count()

    my_sessions_count = 0

    if request.user.is_authenticated:
        if _is_organiser_user(request.user):
            my_sessions_count = base_sessions.filter(created_by=request.user).count()
        else:
            my_sessions_count = base_sessions.filter(
                participants__user=request.user
            ).distinct().count()

    sessions = base_sessions

    if mine_filter:
        if not request.user.is_authenticated:
            return redirect("login")

        if _is_organiser_user(request.user):
            sessions = sessions.filter(created_by=request.user)
        else:
            sessions = sessions.filter(participants__user=request.user).distinct()

    if query:
        sessions = sessions.filter(
            Q(title__icontains=query) |
            Q(location__icontains=query)
        )

    sessions = sessions.annotate(
        participant_count=Count("participants"),
        attended_count=Count("participants", filter=Q(participants__attended=True)),
    )

    if sort == "oldest":
        sessions = sessions.order_by("start_datetime")
    elif sort == "title":
        sessions = sessions.order_by("title")
    else:
        sessions = sessions.order_by("-start_datetime")

    session_rows = []

    for session in sessions:
        session.status_label = _session_status(session)
        session.format_label = _session_format(session)

        if session.participant_count > 0:
            session.attendance_rate = round(
                (session.attended_count / session.participant_count) * 100
            )
        else:
            session.attendance_rate = None

        session.is_full = session.participant_count >= session.capacity

        if request.user.is_authenticated:
            session.user_joined = Participation.objects.filter(
                session=session,
                user=request.user,
            ).exists()
        else:
            session.user_joined = False

        if status_filter == "upcoming" and session.status_label != "Upcoming":
            continue

        if status_filter == "completed" and session.status_label != "Completed":
            continue

        if status_filter == "full" and not session.is_full:
            continue

        if format_filter != "all" and session.format_label.lower() != format_filter:
            continue

        session_rows.append(session)

    total_count = len(session_rows)
    upcoming_count = sum(1 for session in session_rows if session.status_label == "Upcoming")
    completed_count = sum(1 for session in session_rows if session.status_label == "Completed")
    full_count = sum(1 for session in session_rows if session.is_full)

    paginator = Paginator(session_rows, 8)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "scheduling/session_list.html", {
        "page_obj": page_obj,
        "sessions": page_obj.object_list,

        "query": query,
        "status_filter": status_filter,
        "format_filter": format_filter,
        "sort": sort,
        "mine_filter": mine_filter,

        "total_count": total_count,
        "upcoming_count": upcoming_count,
        "completed_count": completed_count,
        "full_count": full_count,

        "all_sessions_count": all_sessions_count,
        "my_sessions_count": my_sessions_count,
    })


@login_required
def session_create(request):
    if not _is_organiser_user(request.user):
        return HttpResponseForbidden("Only organisers can create match sessions.")

    if request.method == "POST":
        form = MatchSessionForm(request.POST)

        if form.is_valid():
            session = form.save(commit=False)
            session.created_by = request.user
            session.save()

            return redirect("session_detail", session_id=session.id)
    else:
        form = MatchSessionForm()

    return render(request, "scheduling/session_create.html", {
        "form": form,
        "is_organiser": True,
    })


def session_detail(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    participants = (
        Participation.objects
        .filter(session=session)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    current_count = participants.count()
    is_full = current_count >= session.capacity
    is_completed = session.start_datetime < timezone.now()
    status_label = "Completed" if is_completed else "Upcoming"

    joined = False
    if request.user.is_authenticated:
        joined = Participation.objects.filter(
            session=session,
            user=request.user,
        ).exists()

    is_organiser = request.user.is_authenticated and request.user == session.created_by

    attended_count = participants.filter(attended=True).count()
    not_marked_count = current_count - attended_count

    attended_percentage = _attendance_percentage(attended_count, current_count)
    not_marked_percentage = _attendance_percentage(not_marked_count, current_count)

    participant_rows = []

    for participation in participants:
        user = participation.user

        try:
            role = user.profile.get_role_display()
        except Exception:
            role = "Player"

        if user == session.created_by:
            role = "Organiser"

        participant_rows.append({
            "participation": participation,
            "user": user,
            "role": role,
            "score": _profile_score(user),
            "peer_rating": _peer_rating_score(user),
        })

    team_a_assignments = (
        TeamAssignment.objects
        .filter(session=session, team=TeamAssignment.TEAM_A)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    team_b_assignments = (
        TeamAssignment.objects
        .filter(session=session, team=TeamAssignment.TEAM_B)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    team_a_rows = []
    team_b_rows = []

    for assignment in team_a_assignments:
        score = _profile_score(assignment.user)

        team_a_rows.append({
            "assignment": assignment,
            "user": assignment.user,
            "score": score,
            "peer_rating": _peer_rating_score(assignment.user),
        })

    for assignment in team_b_assignments:
        score = _profile_score(assignment.user)

        team_b_rows.append({
            "assignment": assignment,
            "user": assignment.user,
            "score": score,
            "peer_rating": _peer_rating_score(assignment.user),
        })

    team_a_total = round(sum(row["score"] for row in team_a_rows), 2)
    team_b_total = round(sum(row["score"] for row in team_b_rows), 2)

    team_a_average = round(team_a_total / len(team_a_rows), 2) if team_a_rows else 0
    team_b_average = round(team_b_total / len(team_b_rows), 2) if team_b_rows else 0

    team_difference = round(abs(team_a_total - team_b_total), 2)
    fairness_score = _team_fairness_score(team_a_total, team_b_total)
    fairness_label = _fairness_label(fairness_score)

    if fairness_score >= 90:
        fairness_class = "fairness-excellent"
    elif fairness_score >= 75:
        fairness_class = "fairness-good"
    elif fairness_score >= 60:
        fairness_class = "fairness-fair"
    else:
        fairness_class = "fairness-warning"

    capacity_percentage = _attendance_percentage(current_count, session.capacity)

    average_session_rating = Rating.objects.filter(session=session).aggregate(
        average=Avg("score")
    )["average"]

    if average_session_rating is not None:
        average_session_rating = round(average_session_rating, 1)

    return render(request, "scheduling/session_detail.html", {
        "session": session,
        "participants": participants,
        "participant_rows": participant_rows,

        "joined": joined,
        "is_full": is_full,
        "is_completed": is_completed,
        "status_label": status_label,
        "is_organiser": is_organiser,

        "current_count": current_count,
        "capacity_percentage": capacity_percentage,

        "attended_count": attended_count,
        "not_marked_count": not_marked_count,
        "attended_percentage": attended_percentage,
        "not_marked_percentage": not_marked_percentage,

        "team_a_rows": team_a_rows,
        "team_b_rows": team_b_rows,
        "team_a_total": team_a_total,
        "team_b_total": team_b_total,
        "team_a_average": team_a_average,
        "team_b_average": team_b_average,
        "team_difference": team_difference,
        "fairness_score": fairness_score,
        "fairness_label": fairness_label,
        "fairness_class": fairness_class,

        "average_session_rating": average_session_rating,
    })

# ===== ATTENDANCE + ML TEAM ALLOCATION HELPERS =====

def _can_manage_session(user, session):
    """
    Only the session creator or a staff user can manage attendance.
    """
    if not user.is_authenticated:
        return False

    if user == session.created_by:
        return True

    if user.is_staff:
        return True

    return False


def _update_user_reliability(user):
    """
    Updates a player's reliability score based on attendance history.
    reliability_score is expected to be between 0.0 and 1.0.
    """
    joined_count = Participation.objects.filter(user=user).count()
    attended_count = Participation.objects.filter(user=user, attended=True).count()

    if joined_count > 0:
        reliability = attended_count / joined_count
    else:
        reliability = 0.0

    try:
        profile = user.profile
        profile.reliability_score = float(reliability)
        profile.save(update_fields=["reliability_score"])
    except Exception:
        pass


def _attendance_status_label(participation):
    if participation.attended:
        return "Attended"

    return "Not marked"


def _attendance_status_class(participation):
    if participation.attended:
        return "attended"

    return "not-marked"


def _safe_profile(user):
    try:
        return user.profile
    except Exception:
        return None


def _normalise_rating_to_five(value):
    """
    Converts old 1-10 values or newer 1-5 values into a safe 1-5 value.
    """
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 3.0

    value = max(1.0, min(value, 10.0))

    if value > 5:
        value = value / 2

    return max(1.0, min(value, 5.0))


def _score_to_percent(value):
    """
    Converts a 1-5 score to a 0-100 percentage for radar charts.
    """
    value = _normalise_rating_to_five(value)
    return round((value / 5) * 100)


def _allocation_position_label(user):
    profile = _safe_profile(user)

    if not profile:
        return "Any"

    display_method = getattr(profile, "get_position_preference_display", None)

    if callable(display_method):
        return display_method()

    value = str(getattr(profile, "position_preference", "ANY")).upper()

    position_map = {
        "GK": "Goalkeeper",
        "DEF": "Defender",
        "MID": "Midfielder",
        "FWD": "Forward",
        "ANY": "Any",
    }

    return position_map.get(value, value.title())


def _allocation_experience_label(user):
    profile = _safe_profile(user)

    if not profile:
        return "Not set"

    display_method = getattr(profile, "get_experience_display", None)

    if callable(display_method):
        return display_method()

    value = str(getattr(profile, "experience", "not_set")).replace("_", " ")

    return value.title()


def _allocation_experience_percent(user):
    profile = _safe_profile(user)

    if not profile:
        return 35

    value = str(getattr(profile, "experience", "")).lower()

    experience_scores = {
        "beginner": 35,
        "intermediate": 70,
        "advanced": 100,
    }

    return experience_scores.get(value, 35)


def _build_player_row(user):
    """
    Builds one row for the Team Allocation page.

    This now uses calculate_player_strength(), which is the same scoring used by
    the ML-assisted allocator.
    """
    profile = _safe_profile(user)

    raw_skill = getattr(profile, "skill_level", 3) if profile else 3
    raw_fitness = getattr(profile, "fitness_level", 3) if profile else 3

    skill = _normalise_rating_to_five(raw_skill)
    fitness = _normalise_rating_to_five(raw_fitness)

    peer_rating = peer_rating_score(user)
    reliability = attendance_reliability_score(user)
    final_score = calculate_player_strength(user)

    display_name = user.get_full_name().strip() or user.username

    return {
        "user": user,
        "username": user.username,
        "name": display_name,

        "position": _allocation_position_label(user),
        "experience": _allocation_experience_label(user),

        "skill": round(skill, 2),
        "fitness": round(fitness, 2),
        "skill_percent": _score_to_percent(skill),
        "fitness_percent": _score_to_percent(fitness),

        "peer_rating": round(peer_rating, 2),
        "peer_rating_percent": _score_to_percent(peer_rating),

        "reliability": round(reliability, 2),
        "reliability_percent": _score_to_percent(reliability),

        "experience_percent": _allocation_experience_percent(user),

        "score": round(final_score, 2),
    }


def _team_metric_average(rows, key):
    if not rows:
        return 0

    total = sum(float(row.get(key, 0) or 0) for row in rows)

    return round(total / len(rows), 1)


def _position_balance_score(rows):
    if not rows:
        return 0

    positions = [
        str(row.get("position", "Any")).lower()
        for row in rows
        if str(row.get("position", "Any")).lower() != "any"
    ]

    if not positions:
        return 50

    unique_positions = len(set(positions))

    return round(min(unique_positions, 4) / 4 * 100)


def _team_radar_data(rows):
    """
    Returns radar chart values out of 100:
    - Skill Level
    - Position Balance
    - Fitness Level
    - Experience
    - Recent Form
    """
    if not rows:
        return [0, 0, 0, 0, 0]

    average_skill = round(
        sum(row["skill_percent"] for row in rows) / len(rows)
    )

    average_fitness = round(
        sum(row["fitness_percent"] for row in rows) / len(rows)
    )

    average_experience = round(
        sum(row["experience_percent"] for row in rows) / len(rows)
    )

    average_recent_form = round(
        sum(row["peer_rating_percent"] for row in rows) / len(rows)
    )

    position_balance = _position_balance_score(rows)

    return [
        average_skill,
        position_balance,
        average_fitness,
        average_experience,
        average_recent_form,
    ]


def _fairness_score(team_a_total, team_b_total):
    if team_a_total <= 0 and team_b_total <= 0:
        return 0

    biggest = max(team_a_total, team_b_total, 1)
    difference = abs(team_a_total - team_b_total)

    score = 100 - ((difference / biggest) * 100)

    return max(0, min(round(score), 100))


def _allocation_fairness_label(score):
    if score >= 90:
        return "Fair"

    if score >= 75:
        return "Mostly Fair"

    if score >= 60:
        return "Acceptable"

    return "Needs Review"


def _allocation_fairness_class(score):
    if score >= 90:
        return "fairness-excellent"

    if score >= 75:
        return "fairness-good"

    if score >= 60:
        return "fairness-warning"

    return "fairness-danger"

@login_required
def generate_teams(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("session_detail", session_id=session.id)

    if request.user != session.created_by and not request.user.is_staff:
        return HttpResponseForbidden("Only the organiser can generate teams.")

    all_participants = (
        Participation.objects
        .filter(session=session)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    attended_count = all_participants.filter(attended=True).count()

    # If attendance has been marked, only use attended players.
    # If nobody has been marked attended yet, use all joined players.
    if attended_count > 0:
        participants = all_participants.filter(attended=True)
        allocation_mode = "attended players only"
    else:
        participants = all_participants
        allocation_mode = "all joined players"

    if participants.count() < 2:
        messages.error(
            request,
            "At least 2 eligible players are needed to generate teams."
        )
        return redirect("session_detail", session_id=session.id)

    allocation = allocate_teams_ml(participants)

    eligible_user_ids = {
        participation.user_id
        for participation in participants
    }

    with transaction.atomic():
        # Delete all old team assignments for this session first.
        TeamAssignment.objects.filter(session=session).delete()

        # Recreate teams using only eligible players.
        for player in allocation["team_a"]:
            if player["user"].id in eligible_user_ids:
                TeamAssignment.objects.create(
                    session=session,
                    user=player["user"],
                    team=TeamAssignment.TEAM_A,
                )

        for player in allocation["team_b"]:
            if player["user"].id in eligible_user_ids:
                TeamAssignment.objects.create(
                    session=session,
                    user=player["user"],
                    team=TeamAssignment.TEAM_B,
                )

    if allocation["used_ml"]:
        messages.success(
            request,
            (
                f"Teams generated using ML-assisted clustering from {allocation_mode}. "
                f"Fairness score: {allocation['fairness_score']}%."
            )
        )
    else:
        messages.warning(
            request,
            (
                f"Teams generated using fallback balancing from {allocation_mode}. "
                f"Fairness score: {allocation['fairness_score']}%. "
                f"{allocation['ml_reason']}"
            )
        )

    return redirect("session_detail", session_id=session.id)

@login_required
def team_allocation(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if not _is_organiser_user(request.user):
        return HttpResponseForbidden("Only organisers can access team allocation.")

    if request.user != session.created_by and not request.user.is_staff:
        return HttpResponseForbidden("Only the session organiser can access this allocation.")


    all_participants = (
    Participation.objects
    .filter(session=session)
    .select_related("user", "user__profile")
    .order_by("user__username")
    )

    attended_count = all_participants.filter(attended=True).count()

    # If attendance has been marked, only show attended players as eligible for allocation.
    # If no attendance has been marked yet, show all joined players.
    if attended_count > 0:
        participants = all_participants.filter(attended=True)
        excluded_participants = all_participants.filter(attended=False)
    else:
        participants = all_participants
        excluded_participants = Participation.objects.none()

    current_count = participants.count()
    team_size = ceil(current_count / 2) if current_count else 0

    team_a_assignments = (
        TeamAssignment.objects
        .filter(session=session, team=TeamAssignment.TEAM_A)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    team_b_assignments = (
        TeamAssignment.objects
        .filter(session=session, team=TeamAssignment.TEAM_B)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    team_a_rows = [
        _build_player_row(assignment.user)
        for assignment in team_a_assignments
    ]

    team_b_rows = [
        _build_player_row(assignment.user)
        for assignment in team_b_assignments
    ]

    allocated_user_ids = set(
        TeamAssignment.objects
        .filter(session=session)
        .values_list("user_id", flat=True)
    )

    unallocated_rows = [
        _build_player_row(participation.user)
        for participation in participants
        if participation.user_id not in allocated_user_ids
    ]

    team_a_total = round(sum(row["score"] for row in team_a_rows), 2)
    team_b_total = round(sum(row["score"] for row in team_b_rows), 2)

    team_a_average = round(team_a_total / len(team_a_rows), 2) if team_a_rows else 0
    team_b_average = round(team_b_total / len(team_b_rows), 2) if team_b_rows else 0

    team_difference = round(abs(team_a_total - team_b_total), 2)

    fairness_score = _fairness_score(team_a_total, team_b_total)
    fairness_label = _allocation_fairness_label(fairness_score)
    fairness_class = _allocation_fairness_class(fairness_score)

    is_ready = current_count >= 2
    has_allocation = bool(team_a_rows or team_b_rows)

    return render(request, "scheduling/team_allocation.html", {
        "session": session,
        "current_count": current_count,
        "team_size": team_size,
        "is_ready": is_ready,
        "has_allocation": has_allocation,

        "team_a_rows": team_a_rows,
        "team_b_rows": team_b_rows,
        "unallocated_rows": unallocated_rows,

        "team_a_total": team_a_total,
        "team_b_total": team_b_total,
        "team_a_average": team_a_average,
        "team_b_average": team_b_average,
        "team_difference": team_difference,

        "fairness_score": fairness_score,
        "fairness_label": fairness_label,
        "fairness_class": fairness_class,

        "radar_labels": [
            "Skill Level",
            "Position Balance",
            "Fitness Level",
            "Experience",
            "Recent Form",
        ],
        "team_a_radar": _team_radar_data(team_a_rows),
        "team_b_radar": _team_radar_data(team_b_rows),

        "ml_note": (
            "ML-assisted allocation uses player skill, fitness, experience, "
            "position preference, attendance reliability, and peer ratings."
        ),
        
        "excluded_count": excluded_participants.count(),

        "sidebar_session_id": session.id,
    })


@login_required
def cancel_team_allocation(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("team_allocation", session_id=session.id)

    if not _is_organiser_user(request.user):
        return HttpResponseForbidden("Only organisers can cancel team allocation.")

    if request.user != session.created_by and not request.user.is_staff:
        return HttpResponseForbidden("Only the session organiser can cancel this allocation.")

    TeamAssignment.objects.filter(session=session).delete()
    messages.success(request, "Team allocation cancelled.")

    return redirect("team_allocation", session_id=session.id)


@login_required
def confirm_team_allocation(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("team_allocation", session_id=session.id)

    if not _is_organiser_user(request.user):
        return HttpResponseForbidden("Only organisers can confirm team allocation.")

    if request.user != session.created_by and not request.user.is_staff:
        return HttpResponseForbidden("Only the session organiser can confirm this allocation.")

    if not TeamAssignment.objects.filter(session=session).exists():
        messages.error(request, "Generate teams before confirming allocation.")
        return redirect("team_allocation", session_id=session.id)

    messages.success(request, "Teams confirmed successfully.")

    return redirect("session_detail", session_id=session.id)

@login_required
def view_teams(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    assignments = (
        TeamAssignment.objects
        .filter(session=session)
        .select_related("user", "user__profile")
        .order_by("team", "user__username")
    )

    team1 = [assignment.user for assignment in assignments if assignment.team == TeamAssignment.TEAM_A]
    team2 = [assignment.user for assignment in assignments if assignment.team == TeamAssignment.TEAM_B]

    total1 = sum(player_strength(user) for user in team1)
    total2 = sum(player_strength(user) for user in team2)

    return render(request, "scheduling/view_teams.html", {
        "session": session,
        "team1": team1,
        "team2": team2,
        "total1": total1,
        "total2": total2,
        "diff": abs(total1 - total2),
    })

def _position_label(user):
    try:
        profile = user.profile
        display_method = getattr(profile, "get_position_preference_display", None)

        if callable(display_method):
            return display_method()

        value = getattr(profile, "position_preference", "ANY")

        position_map = {
            "GK": "Goalkeeper",
            "DEF": "Defender",
            "MID": "Midfielder",
            "FWD": "Forward",
            "ANY": "Any",
            "gk": "Goalkeeper",
            "def": "Defender",
            "mid": "Midfielder",
            "fwd": "Forward",
            "any": "Any",
        }

        return position_map.get(str(value), str(value).title())

    except Exception:
        return "Player"


def _result_player_score(user):
    try:
        profile = user.profile
    except Exception:
        return 0

    experience_scores = {
        "beginner": 1,
        "intermediate": 2,
        "advanced": 3,
    }

    experience_value = experience_scores.get(
        str(getattr(profile, "experience", "")).lower(),
        1
    )

    return (
        getattr(profile, "skill_level", 0)
        + getattr(profile, "fitness_level", 0)
        + experience_value
    )


def _calculate_result_fairness(team_a_users, team_b_users):
    team_a_total = sum(_result_player_score(user) for user in team_a_users)
    team_b_total = sum(_result_player_score(user) for user in team_b_users)

    max_total = max(team_a_total, team_b_total, 1)
    difference = abs(team_a_total - team_b_total)

    fairness_score = round(100 - ((difference / max_total) * 100))
    fairness_score = max(0, min(fairness_score, 100))

    if fairness_score >= 85:
        fairness_label = "Fair"
    elif fairness_score >= 70:
        fairness_label = "Mostly Fair"
    else:
        fairness_label = "Needs Review"

    return fairness_score, fairness_label, difference

@login_required
def match_results(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if session.start_datetime > timezone.now():
        messages.warning(request, "Results are only available after the match is completed.")
        return redirect("session_detail", session_id=session.id)

    participants = (
        Participation.objects
        .filter(session=session)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    current_count = participants.count()
    attended_count = participants.filter(attended=True).count()

    team_a_assignments = (
        TeamAssignment.objects
        .filter(session=session, team=TeamAssignment.TEAM_A)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    team_b_assignments = (
        TeamAssignment.objects
        .filter(session=session, team=TeamAssignment.TEAM_B)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    team_a_users = [assignment.user for assignment in team_a_assignments]
    team_b_users = [assignment.user for assignment in team_b_assignments]

    # fallback if teams have not been generated
    if not team_a_users and not team_b_users:
        participant_users = [participation.user for participation in participants]

        for index, user in enumerate(participant_users):
            if index % 2 == 0:
                team_a_users.append(user)
            else:
                team_b_users.append(user)

    result, created = MatchResult.objects.get_or_create(session=session)

    stats = PlayerMatchStat.objects.filter(session=session).select_related("user")
    stats_map = {
        stat.user_id: stat
        for stat in stats
    }

    def build_team_rows(users):
        rows = []

        for index, user in enumerate(users, start=1):
            stat = stats_map.get(user.id)

            goals = stat.goals if stat else 0
            assists = stat.assists if stat else 0
            rating = float(stat.rating) if stat else 0.0

            rows.append({
                "number": index,
                "user": user,
                "name": user.get_full_name().strip() or user.username,
                "position": _position_label(user),
                "goals": goals,
                "assists": assists,
                "rating": round(rating, 1),
            })

        return rows

    team_a_rows = build_team_rows(team_a_users)
    team_b_rows = build_team_rows(team_b_users)

    team_a_goals = sum(row["goals"] for row in team_a_rows)
    team_b_goals = sum(row["goals"] for row in team_b_rows)

    team_a_assists = sum(row["assists"] for row in team_a_rows)
    team_b_assists = sum(row["assists"] for row in team_b_rows)

    team_a_avg_rating = round(
        sum(row["rating"] for row in team_a_rows) / len(team_a_rows),
        1
    ) if team_a_rows else 0

    team_b_avg_rating = round(
        sum(row["rating"] for row in team_b_rows) / len(team_b_rows),
        1
    ) if team_b_rows else 0

    fairness_score, fairness_label, team_difference = _calculate_result_fairness(
        team_a_users,
        team_b_users,
    )

    mvp = result.mvp

    if not mvp:
        all_rows = team_a_rows + team_b_rows
        if all_rows:
            best_row = sorted(
                all_rows,
                key=lambda row: (row["rating"], row["goals"], row["assists"]),
                reverse=True
            )[0]
            mvp = best_row["user"]

    if mvp:
        mvp_name = mvp.get_full_name().strip() or mvp.username
        mvp_team = "Team A" if mvp in team_a_users else "Team B"
    else:
        mvp_name = "Not selected"
        mvp_team = "-"

    if result.team_a_score > result.team_b_score:
        winner_label = "Team A Wins"
        winner_class = "team-a-wins"
    elif result.team_b_score > result.team_a_score:
        winner_label = "Team B Wins"
        winner_class = "team-b-wins"
    else:
        winner_label = "Draw"
        winner_class = "draw"

    total_goals = result.team_a_score + result.team_b_score

    top_scorer = None
    all_player_rows = team_a_rows + team_b_rows

    if all_player_rows:
        top_scorer = sorted(
            all_player_rows,
            key=lambda row: row["goals"],
            reverse=True,
        )[0]

    return render(request, "scheduling/match_results.html", {
        "session": session,
        "result": result,

        "current_count": current_count,
        "attended_count": attended_count,

        "team_a_rows": team_a_rows,
        "team_b_rows": team_b_rows,

        "team_a_goals": team_a_goals,
        "team_b_goals": team_b_goals,
        "team_a_assists": team_a_assists,
        "team_b_assists": team_b_assists,
        "team_a_avg_rating": team_a_avg_rating,
        "team_b_avg_rating": team_b_avg_rating,

        "fairness_score": fairness_score,
        "fairness_label": fairness_label,
        "team_difference": team_difference,

        "mvp_name": mvp_name,
        "mvp_team": mvp_team,

        "winner_label": winner_label,
        "winner_class": winner_class,

        "total_goals": total_goals,
        "top_scorer": top_scorer,
    })


@login_required
def join_session(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("session_detail", session_id=session.id)

    with transaction.atomic():
        if Participation.objects.filter(session=session, user=request.user).exists():
            return redirect("session_detail", session_id=session.id)

        current_count = (
            Participation.objects
            .select_for_update()
            .filter(session=session)
            .count()
        )

        if current_count >= session.capacity:
            return render(request, "scheduling/session_full.html", {
                "session": session,
            })

        Participation.objects.create(session=session, user=request.user)

    return redirect("session_detail", session_id=session.id)


@login_required
def leave_session(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("session_detail", session_id=session.id)

    # Remove the player from the session
    Participation.objects.filter(
        session=session,
        user=request.user,
    ).delete()

    # Also remove them from generated teams if teams already existed
    TeamAssignment.objects.filter(
        session=session,
        user=request.user,
    ).delete()

    messages.warning(
        request,
        "You left the session. If teams had already been generated, the organiser may need to regenerate them."
    )

    return redirect("session_detail", session_id=session.id)


@login_required
def toggle_attendance(request, session_id, participation_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("session_detail", session_id=session.id)

    if request.user != session.created_by and not request.user.is_staff:
        return HttpResponseForbidden("Only the organiser can mark attendance.")

    participation = get_object_or_404(
        Participation,
        id=participation_id,
        session=session,
    )

    participation.attended = not participation.attended
    participation.save(update_fields=["attended"])

    # If player is marked as not attended, remove them from generated teams
    if not participation.attended:
        TeamAssignment.objects.filter(
            session=session,
            user=participation.user,
        ).delete()

        messages.warning(
            request,
            f"{participation.user.username} was marked as not attended and removed from the team allocation. Regenerate teams to keep them fair."
        )
    else:
        messages.success(
            request,
            f"{participation.user.username} was marked as attended."
        )

    user = participation.user
    joined = Participation.objects.filter(user=user).count()
    attended = Participation.objects.filter(user=user, attended=True).count()

    ratio = (attended / joined) if joined else 0.0

    profile = getattr(user, "profile", None)

    if profile and hasattr(profile, "reliability_score"):
        profile.reliability_score = float(ratio)
        profile.save(update_fields=["reliability_score"])

    return redirect("session_detail", session_id=session.id)


@login_required
def attendance_management(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if not _can_manage_session(request.user, session):
        return HttpResponseForbidden("Only the organiser can manage attendance for this session.")

    query = request.GET.get("q", "").strip()

    all_participants = (
        Participation.objects
        .filter(session=session)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    table_participants = all_participants

    if query:
        table_participants = table_participants.filter(
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__email__icontains=query)
        )

    team_assignments = TeamAssignment.objects.filter(session=session).select_related("user")

    team_map = {
        assignment.user_id: f"Team {assignment.team}"
        for assignment in team_assignments
    }

    total_players = all_participants.count()
    attended_count = all_participants.filter(attended=True).count()
    not_marked_count = total_players - attended_count
    attendance_percentage = _attendance_percentage(attended_count, total_players)

    is_completed = session.start_datetime < timezone.now()

    if is_completed:
        status_label = "Completed"
    elif total_players >= session.capacity:
        status_label = "Full"
    else:
        status_label = "Upcoming"

    participant_rows = []

    for index, participation in enumerate(table_participants, start=1):
        user = participation.user
        display_name = user.get_full_name().strip() or user.username

        try:
            role = user.profile.get_role_display()
        except Exception:
            role = "Player"

        if user == session.created_by:
            role = "Organiser"

        participant_rows.append({
            "number": index,
            "participation": participation,
            "user": user,
            "display_name": display_name,
            "role": role,
            "team": team_map.get(user.id, "Not allocated"),
            "attendance_label": _attendance_status_label(participation),
            "attendance_class": _attendance_status_class(participation),
        })

    return render(request, "scheduling/attendance_management.html", {
        "session": session,
        "query": query,
        "participant_rows": participant_rows,

        "total_players": total_players,
        "attended_count": attended_count,
        "not_marked_count": not_marked_count,
        "attendance_percentage": attendance_percentage,
        "status_label": status_label,
    })


@login_required
def set_attendance_status(request, session_id, participation_id, status):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("attendance_management", session_id=session.id)

    if not _can_manage_session(request.user, session):
        return HttpResponseForbidden("Only the organiser can manage attendance for this session.")

    participation = get_object_or_404(
        Participation,
        id=participation_id,
        session=session,
    )

    if status == "attended":
        participation.attended = True
        message_text = f"{participation.user.username} marked as attended."

    elif status == "not-attended":
        participation.attended = False

        # Remove from teams when marked as not attended
        TeamAssignment.objects.filter(
            session=session,
            user=participation.user,
        ).delete()

        message_text = (
            f"{participation.user.username} marked as not attended and removed from team allocation. "
            "Regenerate teams to keep the allocation fair."
        )

    else:
        messages.error(request, "Invalid attendance status.")
        return redirect("attendance_management", session_id=session.id)

    participation.save(update_fields=["attended"])
    _update_user_reliability(participation.user)

    if status == "not-attended":
        messages.warning(request, message_text)
    else:
        messages.success(request, message_text)

    return redirect("attendance_management", session_id=session.id)


@login_required
def bulk_attendance_action(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("attendance_management", session_id=session.id)

    if not _can_manage_session(request.user, session):
        return HttpResponseForbidden("Only the organiser can manage attendance for this session.")

    action = request.POST.get("action")

    participants = Participation.objects.filter(session=session).select_related("user")

    if action == "mark_all":
        participants.update(attended=True)

        for participation in participants:
            _update_user_reliability(participation.user)

        messages.success(request, "All players have been marked as attended.")

    elif action == "reset":
        participants.update(attended=False)

        for participation in participants:
            _update_user_reliability(participation.user)

        messages.success(request, "Attendance has been reset.")

    else:
        messages.error(request, "Invalid bulk attendance action.")

    return redirect("attendance_management", session_id=session.id)


@login_required
def organiser_dashboard(request):
    if not _is_organiser_user(request.user):
        return HttpResponseForbidden("Only organisers can access this dashboard.")

    sessions_qs = (
        MatchSession.objects
        .filter(created_by=request.user)
        .annotate(
            participant_count=Count("participants"),
            attended_count=Count("participants", filter=Q(participants__attended=True)),
        )
        .order_by("-start_datetime")
    )

    sessions = list(sessions_qs)

    total_sessions = len(sessions)
    total_joined = sum(session.participant_count for session in sessions)
    total_attended = sum(session.attended_count for session in sessions)

    if total_joined > 0:
        attendance_rate = round((total_attended / total_joined) * 100)
    else:
        attendance_rate = 0

    average_rating = Rating.objects.filter(session__in=sessions).aggregate(
        average=Avg("score"),
        count=Count("id"),
    )

    avg_rating = average_rating["average"]
    rating_count = average_rating["count"]

    if avg_rating is not None:
        avg_rating = round(avg_rating, 1)

    now = timezone.now()

    upcoming_count = sum(
        1 for session in sessions
        if session.start_datetime >= now
    )

    completed_count = sum(
        1 for session in sessions
        if session.start_datetime < now
    )

    full_count = sum(
        1 for session in sessions
        if session.participant_count >= session.capacity
    )

    low_attendance_count = 0

    for session in sessions:
        if session.participant_count > 0:
            session.attendance_rate = round((session.attended_count / session.participant_count) * 100)
            session.attendance_style = f"width: {session.attendance_rate}%;"
        else:
            session.attendance_rate = None
            session.attendance_style = "width: 0%;"

        session.is_full = session.participant_count >= session.capacity

        if session.start_datetime < now:
            session.status_label = "Completed"
        elif session.is_full:
            session.status_label = "Full"
        else:
            session.status_label = "Upcoming"

        if session.attendance_rate is not None and session.attendance_rate < 60:
            low_attendance_count += 1

    chart_sessions = sorted(sessions, key=lambda session: session.start_datetime)[-6:]

    chart_labels = [
        session.start_datetime.strftime("%d %b")
        for session in chart_sessions
    ]

    joined_data = [
        session.participant_count
        for session in chart_sessions
    ]

    attended_data = [
        session.attended_count
        for session in chart_sessions
    ]

    status_labels = ["Completed", "Upcoming", "Low Attendance", "Full"]
    status_data = [completed_count, upcoming_count, low_attendance_count, full_count]

    top_player_rows = []

    player_stats = (
        Participation.objects
        .filter(session__in=sessions)
        .values("user__username")
        .annotate(
            joined_count=Count("id"),
            attended_count=Count("id", filter=Q(attended=True)),
        )
    )

    for player in player_stats:
        joined_count = player["joined_count"]
        attended_count = player["attended_count"]

        if joined_count > 0:
            player_rate = round((attended_count / joined_count) * 100)
        else:
            player_rate = 0

        top_player_rows.append({
            "username": player["user__username"],
            "attendance_rate": player_rate,
        })

    top_player_rows = sorted(
        top_player_rows,
        key=lambda player: player["attendance_rate"],
        reverse=True,
    )[:5]

    recent_sessions = sessions[:5]

    return render(request, "scheduling/organiser_dashboard.html", {
        "sessions": sessions,
        "recent_sessions": recent_sessions,

        "total_sessions": total_sessions,
        "total_joined": total_joined,
        "attendance_rate": attendance_rate,
        "avg_rating": avg_rating,
        "rating_count": rating_count,
        "upcoming_count": upcoming_count,
        "completed_count": completed_count,
        "full_count": full_count,
        "low_attendance_count": low_attendance_count,

        "chart_labels": chart_labels,
        "joined_data": joined_data,
        "attended_data": attended_data,

        "status_labels": status_labels,
        "status_data": status_data,

        "top_player_rows": top_player_rows,
        "is_organiser": True,
    })


@login_required
def rate_session(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if not Participation.objects.filter(session=session, user=request.user).exists():
        return HttpResponseForbidden("Join the session before rating.")

    participants = (
        Participation.objects
        .filter(session=session)
        .select_related("user", "user__profile")
        .order_by("user__username")
    )

    ratees = [
        participation.user
        for participation in participants
        if participation.user_id != request.user.id
    ]

    is_completed = timezone.now() >= session.start_datetime
    current_count = participants.count()

    previous_ratings = Rating.objects.filter(rater=request.user)
    total_ratings_given = previous_ratings.count()

    average_rating_given = previous_ratings.aggregate(
        average=Avg("score")
    )["average"]

    if average_rating_given is not None:
        average_rating_given = round(average_rating_given, 1)

    sessions_attended = Participation.objects.filter(
        user=request.user,
        attended=True,
    ).count()

    existing_ratings = {
        rating.ratee_id: rating
        for rating in Rating.objects.filter(session=session, rater=request.user)
    }

    if request.method == "POST":
        saved_count = 0

        for ratee in ratees:
            prefix = f"user_{ratee.id}"
            form = RatingForm(request.POST, prefix=prefix)

            if form.is_valid():
                score = form.cleaned_data.get("score")
                comment = form.cleaned_data.get("comment", "").strip()

                if score:
                    Rating.objects.update_or_create(
                        session=session,
                        rater=request.user,
                        ratee=ratee,
                        defaults={
                            "score": int(score),
                            "comment": comment,
                        },
                    )

                    avg_score = Rating.objects.filter(ratee=ratee).aggregate(
                        average=Avg("score")
                    )["average"] or 0.0

                    if hasattr(ratee, "profile"):
                        ratee.profile.overall_rating = float(avg_score)
                        ratee.profile.save(update_fields=["overall_rating"])

                    saved_count += 1

        if saved_count > 0:
            messages.success(request, f"Saved {saved_count} rating{'' if saved_count == 1 else 's'}.")
        else:
            messages.info(request, "No ratings were selected.")

        return redirect("session_detail", session_id=session.id)

    rating_forms = []

    for ratee in ratees:
        existing = existing_ratings.get(ratee.id)

        initial = {}

        if existing:
            initial = {
                "score": str(existing.score),
                "comment": existing.comment,
            }

        rating_forms.append({
            "user": ratee,
            "form": RatingForm(prefix=f"user_{ratee.id}", initial=initial),
            "existing": existing,
        })

    return render(request, "scheduling/rate_session.html", {
        "session": session,
        "participants": participants,
        "ratees": ratees,
        "rating_forms": rating_forms,

        "is_completed": is_completed,
        "current_count": current_count,

        "total_ratings_given": total_ratings_given,
        "average_rating_given": average_rating_given,
        "sessions_attended": sessions_attended,

        "sidebar_session_id": session.id,
    })