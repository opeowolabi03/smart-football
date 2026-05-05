from django.contrib import admin
from .models import MatchSession, Participation, Rating, TeamAssignment

admin.site.register(MatchSession)
admin.site.register(Participation)
admin.site.register(Rating)
admin.site.register(TeamAssignment)