from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import MatchSession, Participation
from django import forms

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
    participants = Participation.objects.filter(session=session).select_related("user")
    joined = False
    if request.user.is_authenticated:
        joined = Participation.objects.filter(session=session, user=request.user).exists()
    return render(request, "scheduling/session_detail.html", {
        "session": session,
        "participants": participants,
        "joined": joined
    })

@login_required
def join_session(request, session_id):
    session = get_object_or_404(MatchSession, id=session_id)
    Participation.objects.get_or_create(session=session, user=request.user)
    return redirect("session_detail", session_id=session.id)
