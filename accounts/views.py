from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

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

                return redirect("session_list")

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


@login_required
def edit_profile(request):
    profile = request.user.profile

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)

        if form.is_valid():
            form.save()
            return redirect("session_list")
    else:
        form = ProfileForm(instance=profile)

    return render(request, "accounts/edit_profile.html", {"form": form})