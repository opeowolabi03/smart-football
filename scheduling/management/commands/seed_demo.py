from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import random

from scheduling.models import MatchSession, Participation

User = get_user_model()


class Command(BaseCommand):
    help = "Seed demo users + sessions + participation"

    def handle(self, *args, **options):
        organiser, _ = User.objects.get_or_create(username="organiser")
        organiser.set_password("password123")
        organiser.save()

        organiser.profile.role = "organiser"
        organiser.profile.save()

        for i in range(1, 11):
            u, _ = User.objects.get_or_create(username=f"player{i}")
            u.set_password("password123")
            u.save()

            u.profile.skill_level = random.randint(1, 10)
            u.profile.fitness_level = random.randint(1, 10)
            u.profile.position_preference = random.choice(["ANY", "GK", "DEF", "MID", "FWD"])
            u.profile.experience = random.choice(["beginner", "intermediate", "advanced"])
            u.profile.save()

        MatchSession.objects.all().delete()

        for d in range(5):
            s = MatchSession.objects.create(
                title=f"5-a-side Session {d+1}",
                start_datetime=timezone.now() + timedelta(days=d+1),
                location="Sports Hall",
                capacity=10,
                created_by=organiser,
            )

            players = list(User.objects.filter(username__startswith="player"))
            random.shuffle(players)
            for u in players[: random.randint(6, 10)]:
                Participation.objects.get_or_create(session=s, user=u)

        self.stdout.write(self.style.SUCCESS("Seeded demo data. Login: organiser / password123"))