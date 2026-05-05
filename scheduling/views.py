from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django import forms
from .forms import RatingForm
from .models import MatchSession, Participation, Rating, TeamAssignment
from math import ceil
from django.core.paginator import Paginator

def player_strength(user):
    """
    MVP score: weighted self-assessment + peer rating + reliability.
    You can tweak weights later without changing DB.
    """
    p = getattr(user, "profile", None)
    if not p:
        return 0.0

    # skill/fitness are 1..10, overall_rating is 0..5, reliability 0..1-ish
    return (
        (p.skill_level * 1.0) +
        (p.fitness_level * 0.7) +
        (p.overall_rating * 2.0) +
        (p.reliability_score * 2.0)
    )



class MatchSessionForm(forms.ModelForm):
    class Meta:
        model = MatchSession
        fields = ["title", "start_datetime", "location", "capacity"]

def _stars_from_ten(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0

    filled = ceil(max(0, min(value, 10)) / 2)
    return "★" * filled + "☆" * (5 - filled)


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
        "skill_stars": _stars_from_ten(getattr(profile, "skill_level", 0) if profile else 0),
        "fitness_stars": _stars_from_ten(getattr(profile, "fitness_level", 0) if profile else 0),
        "position": _display_choice(profile, "position_preference"),
        "experience": _display_choice(profile, "experience"),
    }

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
    })

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


def session_list(request):
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")
    format_filter = request.GET.get("format", "all")
    sort = request.GET.get("sort", "newest")

    sessions = (
        MatchSession.objects
        .all()
        .annotate(
            participant_count=Count("participants"),
            attended_count=Count("participants", filter=Q(participants__attended=True)),
        )
    )

    if query:
        sessions = sessions.filter(
            Q(title__icontains=query) |
            Q(location__icontains=query)
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
            session.attendance_rate = round((session.attended_count / session.participant_count) * 100)
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

        if status_filter != "all" and session.status_label.lower() != status_filter:
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
        "total_count": total_count,
        "upcoming_count": upcoming_count,
        "completed_count": completed_count,
        "full_count": full_count,
    })

@login_required
def session_create(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Only organisers can create sessions.")

    if request.method == "POST":
        form = MatchSessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.created_by = request.user
            session.save()
            return redirect("session_detail", session_id=session.id)
    else:
        form = MatchSessionForm()
    return render(request, "scheduling/session_create.html", {"form": form})


from django.shortcuts import get_object_or_404, render
# make sure TeamAssignment is imported at the top:
# from .models import MatchSession, Participation, TeamAssignment

def _profile_score(user):
    try:
        profile = user.profile
    except Exception:
        return 0

    experience_scores = {
        "beginner": 1,
        "intermediate": 2,
        "advanced": 3,
    }

    experience_value = experience_scores.get(str(getattr(profile, "experience", "")).lower(), 1)

    return (
        (getattr(profile, "skill_level", 0) * 2)
        + getattr(profile, "fitness_level", 0)
        + experience_value
    )


def _attendance_percentage(count, total):
    if total <= 0:
        return 0

    return round((count / total) * 100)


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
        joined = Participation.objects.filter(session=session, user=request.user).exists()

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
        })

    for assignment in team_b_assignments:
        score = _profile_score(assignment.user)
        team_b_rows.append({
            "assignment": assignment,
            "user": assignment.user,
            "score": score,
        })

    team_a_total = sum(row["score"] for row in team_a_rows)
    team_b_total = sum(row["score"] for row in team_b_rows)

    team_a_average = round(team_a_total / len(team_a_rows), 1) if team_a_rows else 0
    team_b_average = round(team_b_total / len(team_b_rows), 1) if team_b_rows else 0

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

        "average_session_rating": average_session_rating,
    })

@login_required
def generate_teams(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    # Only allow POST (button click)
    if request.method != "POST":
        return redirect("session_detail", session_id=session.id)

    # Organiser-only: creator generates teams
    if request.user != session.created_by:
        return HttpResponseForbidden("Only the organiser can generate teams.")

    participants = (
        Participation.objects
        .filter(session=session)
        .select_related("user", "user__profile")
    )

    if participants.count() < 2:
        return redirect("session_detail", session_id=session.id)

    # Build list of (user, score)
    player_scores = []
    for p in participants:
        prof = p.user.profile

        # experience_weight() exists in your Profile model
        exp = prof.experience_weight() if hasattr(prof, "experience_weight") else 1

        # simple weighted score (easy to explain in demo)
        score = (prof.skill_level * 2) + prof.fitness_level + exp
        player_scores.append((p.user, score))

    # Sort best -> worst
    player_scores.sort(key=lambda x: x[1], reverse=True)

    # Greedy balancing
    team_a, team_b = [], []
    sum_a, sum_b = 0.0, 0.0

    for user, score in player_scores:
        if sum_a <= sum_b:
            team_a.append(user)
            sum_a += score
        else:
            team_b.append(user)
            sum_b += score

    # Save assignments
    with transaction.atomic():
        TeamAssignment.objects.filter(session=session).delete()

        for user in team_a:
            TeamAssignment.objects.create(session=session, user=user, team=TeamAssignment.TEAM_A)

        for user in team_b:
            TeamAssignment.objects.create(session=session, user=user, team=TeamAssignment.TEAM_B)

    return redirect("session_detail", session_id=session.id)

@login_required
def view_teams(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    from .models import TeamAssignment

    assignments = (
        TeamAssignment.objects.filter(session=session)
        .select_related("user", "user__profile")
        .order_by("team", "user__username")
    )

    team1 = [a.user for a in assignments if a.team == 1]
    team2 = [a.user for a in assignments if a.team == 2]

    # show a basic "balance metric"
    total1 = sum(player_strength(u) for u in team1)
    total2 = sum(player_strength(u) for u in team2)

    return render(request, "scheduling/view_teams.html", {
        "session": session,
        "team1": team1,
        "team2": team2,
        "total1": total1,
        "total2": total2,
        "diff": abs(total1 - total2),
    })


@login_required
def join_session(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("session_detail", session_id=session.id)

    with transaction.atomic():
        if Participation.objects.filter(session=session, user=request.user).exists():
            return redirect("session_detail", session_id=session.id)

        current_count = Participation.objects.select_for_update().filter(session=session).count()
        if current_count >= session.capacity:
            return render(request, "scheduling/session_full.html", {"session": session})

        Participation.objects.create(session=session, user=request.user)

    return redirect("session_detail", session_id=session.id)


@login_required
def leave_session(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("session_detail", session_id=session.id)

    Participation.objects.filter(session=session, user=request.user).delete()
    return redirect("session_detail", session_id=session.id)


@login_required
def toggle_attendance(request, session_id, participation_id):
    session = get_object_or_404(MatchSession, id=session_id)

    if request.method != "POST":
        return redirect("session_detail", session_id=session.id)

    if request.user != session.created_by:
        return HttpResponseForbidden("Only the organiser can mark attendance.")

    participation = get_object_or_404(Participation, id=participation_id, session=session)
    participation.attended = not participation.attended
    participation.save(update_fields=["attended"])

    # Part Z1: update reliability_score for that user (attended / joined)
    u = participation.user
    joined = Participation.objects.filter(user=u).count()
    attended = Participation.objects.filter(user=u, attended=True).count()
    ratio = (attended / joined) if joined else 0.0

    if hasattr(u, "profile"):
        u.profile.reliability_score = float(ratio)
        u.profile.save(update_fields=["reliability_score"])

    return redirect("session_detail", session_id=session.id)

@login_required
def organiser_dashboard(request):
    sessions = (
        MatchSession.objects
        .filter(created_by=request.user)
        .annotate(
            participant_count=Count("participants"),
            attended_count=Count("participants", filter=Q(participants__attended=True)),
        )
        .order_by("start_datetime")
    )

    labels = [s.start_datetime.strftime("%d %b") for s in sessions]
    joined_data = [s.participant_count for s in sessions]
    attended_data = [s.attended_count for s in sessions]

    return render(request, "scheduling/organiser_dashboard.html", {
        "sessions": sessions,
        "labels": labels,
        "joined_data": joined_data,
        "attended_data": attended_data,
    })

@login_required
def rate_session(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)

    # must have joined
    if not Participation.objects.filter(session=session, user=request.user).exists():
        return HttpResponseForbidden("Join the session before rating.")

    # only after session time (basic rule)
    if timezone.now() < session.start_datetime:
        return HttpResponseForbidden("You can rate after the session time.")

    participants = (
        Participation.objects.filter(session=session)
        .select_related("user")
        .order_by("user__username")
    )

    # people you can rate (exclude yourself)
    ratees = [p.user for p in participants if p.user_id != request.user.id]

    if request.method == "POST":
        # handle multiple forms in one post
        for u in ratees:
            prefix = f"user_{u.id}"
            form = RatingForm(request.POST, prefix=prefix)
            if form.is_valid():
                score = form.cleaned_data["score"]
                comment = form.cleaned_data["comment"]

                Rating.objects.update_or_create(
                    session=session,
                    rater=request.user,
                    ratee=u,
                    defaults={"score": score, "comment": comment},
                )

        # update overall_rating for each ratee (simple avg of all received ratings)
        for u in ratees:
            avg_score = Rating.objects.filter(ratee=u).aggregate(avg=Avg("score"))["avg"] or 0.0
            if hasattr(u, "profile"):
                u.profile.overall_rating = float(avg_score)
                u.profile.save(update_fields=["overall_rating"])

        messages.success(request, "Ratings saved.")
        return redirect("session_detail", session_id=session.id)

    forms = []
    existing = {
        r.ratee_id: r for r in Rating.objects.filter(session=session, rater=request.user)
    }
    for u in ratees:
        initial = {}
        if u.id in existing:
            initial = {"ratee_id": u.id, "score": existing[u.id].score, "comment": existing[u.id].comment}
        else:
            initial = {"ratee_id": u.id, "score": 3, "comment": ""}

        forms.append((u, RatingForm(prefix=f"user_{u.id}", initial=initial)))

    return render(request, "scheduling/rate_session.html", {"session": session, "forms": forms})
