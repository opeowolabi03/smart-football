from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Profile(models.Model):
    ROLE_PLAYER = "player"
    ROLE_ORGANISER = "organiser"

    ROLE_CHOICES = [
        (ROLE_PLAYER, "Player"),
        (ROLE_ORGANISER, "Organiser"),
    ]

    POSITION_ANY = "any"
    POSITION_GK = "gk"
    POSITION_DEF = "def"
    POSITION_MID = "mid"
    POSITION_FWD = "fwd"

    POSITION_CHOICES = [
        (POSITION_ANY, "Any"),
        (POSITION_GK, "Goalkeeper"),
        (POSITION_DEF, "Defender"),
        (POSITION_MID, "Midfielder"),
        (POSITION_FWD, "Forward"),
    ]

    EXP_BEGINNER = "beginner"
    EXP_INTERMEDIATE = "intermediate"
    EXP_ADVANCED = "advanced"

    EXPERIENCE_CHOICES = [
        (EXP_BEGINNER, "Beginner"),
        (EXP_INTERMEDIATE, "Intermediate"),
        (EXP_ADVANCED, "Advanced"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

 
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_PLAYER)

    # self-assessment inputs (for balancing)
    skill_level = models.PositiveIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])
    fitness_level = models.PositiveIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])
    position_preference = models.CharField(max_length=10, choices=POSITION_CHOICES, default=POSITION_ANY)
    experience = models.CharField(max_length=20, choices=EXPERIENCE_CHOICES, default=EXP_BEGINNER)

    
    overall_rating = models.FloatField(default=0.0)       
    reliability_score = models.FloatField(default=0.0)   

    def __str__(self):
        return f"{self.user.username} ({self.role})"
