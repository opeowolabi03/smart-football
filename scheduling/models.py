from django.conf import settings
from django.db import models

class MatchSession(models.Model):
    title = models.CharField(max_length=100)
    start_datetime = models.DateTimeField()
    location = models.CharField(max_length=200)
    capacity = models.PositiveIntegerField(default=10)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_sessions"
    )

    def __str__(self):
        return f"{self.title} @ {self.start_datetime:%Y-%m-%d %H:%M}"

class Participation(models.Model):
    session = models.ForeignKey(MatchSession, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    attended = models.BooleanField(default=False)

    class Meta:
        unique_together = ("session", "user")

    def __str__(self):
        return f"{self.user.username} in {self.session.title}"
