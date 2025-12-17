from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django import forms
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden

from .models import MatchSession, Participation


class MatchSessionForm(forms.ModelForm):
    class Meta:
        model = MatchSession
        fields = ["title", "start_datetime", "location", "capacity"]


def session_list(request):
    sessions = MatchSession.objects.filter(start_datetime__gte=timezone.now()).order_by("start_datetime")
    return render(request, "scheduling/session_list.html", {"sessions": sessions})


@login_required
def session_create(request):
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


def session_detail(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)
    participants = Participation.objects.filter(session=session).select_related("user").order_by("user__username")

    joined = False
    if request.user.is_authenticated:
        joined = Participation.objects.filter(session=session, user=request.user).exists()

    current_count = Participation.objects.filter(session=session).count()
    is_full = current_count >= session.capacity

    return render(request, "scheduling/session_detail.html", {
        "session": session,
        "participants": participants,
        "joined": joined,
        "is_full": is_full,
        "current_count": current_count,
        "is_organiser": request.user.is_authenticated and (request.user == session.created_by),
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

    # Only organiser (session creator) can do this
    if request.user != session.created_by:
        return HttpResponseForbidden("Only the organiser can mark attendance.")

    participation = get_object_or_404(Participation, id=participation_id, session=session)
    participation.attended = not participation.attended
    participation.save(update_fields=["attended"])

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
        .order_by("-start_datetime")
    )
    return render(request, "scheduling/organiser_dashboard.html", {"sessions": sessions})
