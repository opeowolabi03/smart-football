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


def session_list(request):
    sessions = MatchSession.objects.all().order_by("start_datetime")
    return render(request, "scheduling/session_list.html", {"sessions": sessions})


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

def session_detail(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)
    participants = Participation.objects.filter(session=session).select_related("user").order_by("user__username")

    joined = False
    if request.user.is_authenticated:
        joined = Participation.objects.filter(session=session, user=request.user).exists()

    current_count = Participation.objects.filter(session=session).count()
    is_full = current_count >= session.capacity

    # NEW: fetch saved teams
    team_a = TeamAssignment.objects.filter(
        session=session, team=TeamAssignment.TEAM_A
    ).select_related("user").order_by("user__username")

    team_b = TeamAssignment.objects.filter(
        session=session, team=TeamAssignment.TEAM_B
    ).select_related("user").order_by("user__username")

    return render(request, "scheduling/session_detail.html", {
        "session": session,
        "participants": participants,
        "joined": joined,
        "is_full": is_full,
        "current_count": current_count,
        "team_a": team_a,     # NEW
        "team_b": team_b,     # NEW
        "is_organiser": request.user.is_authenticated and (request.user == session.created_by),
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
