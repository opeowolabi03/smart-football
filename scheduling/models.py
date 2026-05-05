from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class MatchSession(models.Model):
    title = models.CharField(max_length=100)
    start_datetime = models.DateTimeField()
    location = models.CharField(max_length=200)
    capacity = models.PositiveIntegerField(default=10)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_sessions",
    )

    def __str__(self):
        return f"{self.title} @ {self.start_datetime:%Y-%m-%d %H:%M}"


class Participation(models.Model):
    session = models.ForeignKey(
        MatchSession,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    attended = models.BooleanField(default=False)

    class Meta:
        unique_together = ("session", "user")

    def __str__(self):
        return f"{self.user.username} in {self.session.title}"


class Rating(models.Model):
    session = models.ForeignKey(
        MatchSession,
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ratings_given",
    )
    ratee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ratings_received",
    )

    score = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("session", "rater", "ratee")

    def __str__(self):
        return f"{self.session_id}: {self.rater_id} -> {self.ratee_id} ({self.score})"


class TeamAssignment(models.Model):
    TEAM_A = "A"
    TEAM_B = "B"
    TEAM_CHOICES = [
        (TEAM_A, "Team A"),
        (TEAM_B, "Team B"),
    ]

    session = models.ForeignKey(
        MatchSession,
        on_delete=models.CASCADE,
        related_name="team_assignments",
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    team = models.CharField(max_length=1, choices=TEAM_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("session", "user")

    def __str__(self):
        return f"{self.user.username} -> Team {self.team} ({self.session.title})"