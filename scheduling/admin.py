from django.contrib import admin

try:
    from .models import MatchSession, Participation, Rating, TeamAssignment
    admin.site.register(MatchSession)
    admin.site.register(Participation)
    admin.site.register(Rating)
    admin.site.register(TeamAssignment)
except Exception as e:
    # prevents Django admin autodiscover from crashing the whole project
    print("Admin model import failed:", e)