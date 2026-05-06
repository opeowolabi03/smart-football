def role_navigation(request):
    user = getattr(request, "user", None)
    is_organiser = False

    if user and user.is_authenticated:
        if user.is_staff:
            is_organiser = True
        else:
            try:
                is_organiser = str(user.profile.role).lower() == "organiser"
            except Exception:
                is_organiser = False

    return {
        "global_is_organiser": is_organiser,
    }