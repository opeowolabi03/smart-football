from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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
    score = models.PositiveIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ]
    )
    comment = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("session", "rater", "ratee")

    def __str__(self):
        return f"{self.session.title}: {self.rater.username} rated {self.ratee.username} {self.score}/5"


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
    
class MatchResult(models.Model):
    session = models.OneToOneField(
        MatchSession,
        on_delete=models.CASCADE,
        related_name="result",
    )

    team_a_score = models.PositiveIntegerField(default=0)
    team_b_score = models.PositiveIntegerField(default=0)

    team_a_possession = models.PositiveIntegerField(default=50)
    team_b_possession = models.PositiveIntegerField(default=50)

    team_a_shots = models.PositiveIntegerField(default=0)
    team_b_shots = models.PositiveIntegerField(default=0)

    team_a_chances = models.PositiveIntegerField(default=0)
    team_b_chances = models.PositiveIntegerField(default=0)

    team_a_pass_accuracy = models.PositiveIntegerField(default=0)
    team_b_pass_accuracy = models.PositiveIntegerField(default=0)

    team_a_tackles = models.PositiveIntegerField(default=0)
    team_b_tackles = models.PositiveIntegerField(default=0)

    mvp = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mvp_results",
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def winner_label(self):
        if self.team_a_score > self.team_b_score:
            return "Team A Wins"
        if self.team_b_score > self.team_a_score:
            return "Team B Wins"
        return "Draw"

    def __str__(self):
        return f"{self.session.title}: {self.team_a_score} - {self.team_b_score}"


class PlayerMatchStat(models.Model):
    session = models.ForeignKey(
        MatchSession,
        on_delete=models.CASCADE,
        related_name="player_stats",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="match_stats",
    )

    goals = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)

    class Meta:
        unique_together = ("session", "user")

    def __str__(self):
        return f"{self.user.username} stats for {self.session.title}"

