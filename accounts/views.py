from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from math import ceil

from django.db.models import Avg

from scheduling.models import Participation, Rating

from .forms import LoginForm, ProfileForm, SignUpForm


def auth_page(request, mode="login"):
    login_form = LoginForm(request)
    signup_form = SignUpForm()
    active_panel = mode

    if request.method == "POST":
        if "login_submit" in request.POST:
            active_panel = "login"
            login_form = LoginForm(request, data=request.POST)
            signup_form = SignUpForm()

            if login_form.is_valid():
                auth_login(request, login_form.get_user())

                if not request.POST.get("remember_me"):
                    request.session.set_expiry(0)

                return redirect("player_dashboard")

        elif "signup_submit" in request.POST:
            active_panel = "signup"
            signup_form = SignUpForm(request.POST)
            login_form = LoginForm(request)

            if signup_form.is_valid():
                user = signup_form.save()
                auth_login(request, user)
                return redirect("edit_profile")

    return render(request, "accounts/auth.html", {
        "login_form": login_form,
        "signup_form": signup_form,
        "active_panel": active_panel,
    })

def _football_rating(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0

    value = max(0, min(value, 5))

    return {
        "value": value,
        "balls": [i <= value for i in range(1, 6)],
    }


def _display_choice(obj, field_name, default="Not set"):
    display_method = getattr(obj, f"get_{field_name}_display", None)

    if callable(display_method):
        return display_method()

    value = getattr(obj, field_name, default)

    label_map = {
        "ANY": "Any",
        "any": "Any",
        "GK": "Goalkeeper",
        "DEF": "Defender",
        "MID": "Midfielder",
        "FWD": "Forward",
        "beginner": "Beginner",
        "intermediate": "Intermediate",
        "advanced": "Advanced",
        "player": "Player",
        "organiser": "Organiser",
    }

    return label_map.get(str(value), str(value).replace("_", " ").title())


@login_required
def edit_profile(request):
    profile = request.user.profile

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)

        if form.is_valid():
            form.save()
            return redirect("player_dashboard")
    else:
        form = ProfileForm(instance=profile)

    matches_joined = Participation.objects.filter(user=request.user).count()

    average_rating = Rating.objects.filter(ratee=request.user).aggregate(
        average=Avg("score")
    )["average"]

    if average_rating is not None:
        average_rating = round(average_rating, 1)

    display_name = request.user.get_full_name().strip() or request.user.username

    profile_summary = {
        "name": display_name,
        "username": request.user.username,
        "email": request.user.email or "No email set",
        "role": _display_choice(profile, "role", "Player"),
        "skill": _football_rating(profile.skill_level),
        "fitness": _football_rating(profile.fitness_level),
        "position": _display_choice(profile, "position_preference"),
        "experience": _display_choice(profile, "experience"),
        "matches_joined": matches_joined,
        "average_rating": average_rating,
        "date_joined": request.user.date_joined,
    }

    return render(request, "accounts/edit_profile.html", {
        "form": form,
        "profile_summary": profile_summary,
    })