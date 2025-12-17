from django.conf import settings
from django.db import models

class Profile(models.Model):
    ROLE_PLAYER = "player"
    ROLE_ORGANISER = "organiser"

    ROLE_CHOICES = [
        (ROLE_PLAYER, "Player"),
        (ROLE_ORGANISER, "Organiser"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_PLAYER)

    def __str__(self):
        return f"{self.user.username} ({self.role})"
