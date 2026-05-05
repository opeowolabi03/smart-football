from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .forms import ProfileForm


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("login")
    else:
        form = UserCreationForm()

    return render(request, "accounts/signup.html", {"form": form})


@login_required
def edit_profile(request):
    profile = request.user.profile

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("session_list")  # better than redirecting back to itself
    else:
        form = ProfileForm(instance=profile)

    return render(request, "accounts/edit_profile.html", {"form": form})