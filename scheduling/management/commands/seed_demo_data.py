from datetime import timedelta
import random

from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile
from scheduling.models import MatchSession, Participation, TeamAssignment, Rating


class Command(BaseCommand):
    help = "Seed Smart Football with realistic dissertation demo data."

    PASSWORD = "password123"

    def handle(self, *args, **options):
        with transaction.atomic():
            self.clear_demo_data()

            organisers = self.create_organisers()
            players = self.create_players()
            sessions = self.create_sessions(organisers)
            self.create_participation_and_attendance(sessions, players)
            self.create_team_assignments(sessions)
            self.create_ratings(sessions)

        self.stdout.write(self.style.SUCCESS("Demo data created successfully."))
        self.stdout.write("")
        self.stdout.write("Login password for all demo users: password123")
        self.stdout.write("")
        self.stdout.write("Example player logins:")
        self.stdout.write("  amelia_brown / password123")
        self.stdout.write("  joshua_wilson / password123")
        self.stdout.write("  grace_thompson / password123")
        self.stdout.write("")
        self.stdout.write("Example organiser logins:")
        self.stdout.write("  organiser_james / password123")
        self.stdout.write("  organiser_sophia / password123")

    def clear_demo_data(self):
        """
        Clears demo data only.
        Does NOT delete database tables.
        Does NOT delete Django migrations/content types/permissions.
        Keeps superusers, so your admin account survives, because we are not monsters.
        """

        self.stdout.write("Clearing existing demo data...")

        Rating.objects.all().delete()
        TeamAssignment.objects.all().delete()
        Participation.objects.all().delete()
        MatchSession.objects.all().delete()

        Session.objects.all().delete()
        LogEntry.objects.all().delete()

        User = get_user_model()

        # Delete all non-superuser accounts so the database contains a clean demo set.
        Profile.objects.filter(user__is_superuser=False).delete()
        User.objects.filter(is_superuser=False).delete()

    def create_organisers(self):
        User = get_user_model()

        organiser_data = [
            ("organiser_james", "James", "Carter"),
            ("organiser_sophia", "Sophia", "Mitchell"),
            ("organiser_lewis", "Lewis", "Hughes"),
            ("organiser_olivia", "Olivia", "Turner"),
            ("organiser_daniel", "Daniel", "Roberts"),
        ]

        organisers = []

        for username, first_name, last_name in organiser_data:
            user = User.objects.create_user(
                username=username,
                password=self.PASSWORD,
                first_name=first_name,
                last_name=last_name,
                email=f"{username}@smartfootball.demo",
                is_staff=True,
            )

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = "organiser"
            profile.skill_level = 5
            profile.position_preference = "ANY"
            profile.fitness_level = 5
            profile.experience = "organiser"
            profile.overall_rating = 0.0
            profile.reliability_score = 100.0
            profile.save()

            organisers.append(user)

        return organisers

    def create_players(self):
        User = get_user_model()

        player_data = [
            # username, first, last, skill, position, fitness, experience, rating, reliability
            ("amelia_brown", "Amelia", "Brown", 9, "MID", 9, "advanced", 4.8, 100.0),
            ("joshua_wilson", "Joshua", "Wilson", 8, "DEF", 8, "advanced", 4.7, 100.0),

            ("grace_thompson", "Grace", "Thompson", 7, "FWD", 8, "advanced", 4.4, 88.0),
            ("ethan_clarke", "Ethan", "Clarke", 6, "MID", 7, "intermediate", 4.1, 82.0),
            ("maya_patel", "Maya", "Patel", 5, "ANY", 7, "intermediate", 3.9, 76.0),
            ("noah_evans", "Noah", "Evans", 4, "DEF", 6, "intermediate", 3.6, 70.0),
            ("chloe_morgan", "Chloe", "Morgan", 3, "GK", 6, "beginner", 3.4, 68.0),
            ("oliver_reed", "Oliver", "Reed", 8, "FWD", 9, "advanced", 4.6, 90.0),
            ("lily_anderson", "Lily", "Anderson", 2, "ANY", 5, "beginner", 3.2, 62.0),
            ("samuel_price", "Samuel", "Price", 6, "MID", 7, "intermediate", 4.0, 75.0),

            ("isla_harris", "Isla", "Harris", 7, "DEF", 8, "advanced", 4.3, 84.0),
            ("harry_walker", "Harry", "Walker", 5, "GK", 7, "intermediate", 3.8, 78.0),
            ("ava_robinson", "Ava", "Robinson", 4, "ANY", 6, "beginner", 3.5, 66.0),
            ("leo_white", "Leo", "White", 9, "FWD", 9, "advanced", 4.9, 92.0),
            ("freya_hall", "Freya", "Hall", 6, "DEF", 7, "intermediate", 4.0, 73.0),
            ("mason_green", "Mason", "Green", 3, "MID", 6, "beginner", 3.3, 64.0),
            ("ella_king", "Ella", "King", 8, "ANY", 8, "advanced", 4.5, 86.0),
            ("jacob_scott", "Jacob", "Scott", 5, "FWD", 7, "intermediate", 3.9, 74.0),
            ("ruby_adams", "Ruby", "Adams", 4, "GK", 5, "beginner", 3.5, 69.0),
            ("archie_baker", "Archie", "Baker", 7, "MID", 8, "advanced", 4.2, 80.0),

            ("mia_nelson", "Mia", "Nelson", 2, "DEF", 5, "beginner", 3.1, 58.0),
            ("logan_cooper", "Logan", "Cooper", 6, "ANY", 7, "intermediate", 4.0, 72.0),
            ("zara_morris", "Zara", "Morris", 5, "MID", 6, "intermediate", 3.8, 71.0),
            ("benjamin_ward", "Benjamin", "Ward", 3, "FWD", 6, "beginner", 3.4, 63.0),
            ("nina_russell", "Nina", "Russell", 7, "ANY", 8, "advanced", 4.3, 83.0),
        ]

        players = []

        for username, first_name, last_name, skill, position, fitness, experience, rating, reliability in player_data:
            user = User.objects.create_user(
                username=username,
                password=self.PASSWORD,
                first_name=first_name,
                last_name=last_name,
                email=f"{username}@smartfootball.demo",
                is_staff=False,
            )

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = "player"
            profile.skill_level = skill
            profile.position_preference = position
            profile.fitness_level = fitness
            profile.experience = experience
            profile.overall_rating = rating
            profile.reliability_score = reliability
            profile.save()

            players.append(user)

        return players

    def create_sessions(self, organisers):
        now = timezone.now()

        session_data = [
            # title, days offset, hour, minute, location, capacity, organiser index
            ("Monday Night 5-a-side", -35, 18, 30, "Derby Sports Centre", 10, 0),
            ("Community Cup Practice", -28, 19, 0, "Markeaton Park Pitch", 10, 1),
            ("Riverside Friendly", -21, 17, 30, "Riverside Football Courts", 12, 2),
            ("Friday Skills Match", -14, 20, 0, "Powerleague Derby", 10, 3),
            ("Derby Social Football", -9, 18, 0, "University Sports Hall", 8, 4),
            ("Late Evening Kickabout", -4, 19, 45, "Alvaston Park Pitch", 14, 0),

            ("Tuesday 5-a-side", 2, 18, 30, "Derby Sports Centre", 10, 1),
            ("Saturday Community Match", 5, 11, 0, "Markeaton Park Pitch", 12, 2),
            ("Beginner Friendly Game", 8, 16, 0, "University Sports Hall", 10, 3),
            ("Advanced Balance Trial", 12, 19, 0, "Powerleague Derby", 10, 4),
            ("Open Training Session", 18, 18, 0, "Riverside Football Courts", 16, 0),
            ("End of Month Friendly", 24, 17, 30, "Alvaston Park Pitch", 14, 1),
        ]

        sessions = []

        for title, days_offset, hour, minute, location, capacity, organiser_index in session_data:
            base_date = now + timedelta(days=days_offset)
            start_datetime = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

            session = MatchSession.objects.create(
                title=title,
                start_datetime=start_datetime,
                location=location,
                capacity=capacity,
                created_by=organisers[organiser_index],
            )

            sessions.append(session)

        return sessions

    def create_participation_and_attendance(self, sessions, players):
        """
        Creates:
        - full past matches
        - partially filled past matches
        - mixed attendance
        - one past match with no attendance marked
        - full upcoming matches
        - partially filled upcoming matches

        Amelia Brown and Joshua Wilson have 100% attendance for every past match they join.
        """

        rosters = {
            "Monday Night 5-a-side": {
                "players": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
                "attendance": "all",
            },
            "Community Cup Practice": {
                "players": [0, 1, 10, 11, 12, 13, 14, 15, 16, 17],
                "attendance": 8,
            },
            "Riverside Friendly": {
                "players": [0, 1, 3, 5, 7, 9, 11, 13, 15],
                "attendance": 6,
            },
            "Friday Skills Match": {
                # Does not include Amelia/Joshua, so this can be fully unmarked.
                "players": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
                "attendance": "none",
            },
            "Derby Social Football": {
                "players": [0, 1, 18, 19, 20, 21, 22, 23],
                "attendance": 5,
            },
            "Late Evening Kickabout": {
                "players": [0, 1, 2, 6, 10, 14, 18, 22, 24, 5, 9],
                "attendance": 9,
            },

            "Tuesday 5-a-side": {
                "players": [0, 1, 2, 3, 7, 10, 13, 16, 19, 24],
                "attendance": "upcoming",
            },
            "Saturday Community Match": {
                "players": [0, 1, 4, 5, 11, 17, 21],
                "attendance": "upcoming",
            },
            "Beginner Friendly Game": {
                "players": [6, 8, 12, 20, 23],
                "attendance": "upcoming",
            },
            "Advanced Balance Trial": {
                "players": [0, 1, 2, 7, 10, 13, 16, 19, 21, 24],
                "attendance": "upcoming",
            },
            "Open Training Session": {
                "players": [3, 4, 5, 9, 14, 22],
                "attendance": "upcoming",
            },
            "End of Month Friendly": {
                "players": [0, 1, 2, 3, 4, 7, 10, 13, 16, 17, 19, 24],
                "attendance": "upcoming",
            },
        }

        for session in sessions:
            config = rosters[session.title]
            player_indexes = config["players"]
            attendance_rule = config["attendance"]

            for order, player_index in enumerate(player_indexes):
                user = players[player_index]

                attended = False

                if attendance_rule == "all":
                    attended = True
                elif attendance_rule == "none":
                    attended = False
                elif attendance_rule == "upcoming":
                    attended = False
                elif isinstance(attendance_rule, int):
                    attended = order < attendance_rule

                    # Force 100% attendance for these two whenever they are in a past match.
                    if user.username in ["amelia_brown", "joshua_wilson"]:
                        attended = True

                Participation.objects.create(
                    session=session,
                    user=user,
                    attended=attended,
                )

    def create_team_assignments(self, sessions):
        """
        Assigns players to Team A and Team B for sessions that have enough participants.
        Uses a simple greedy balancing approach based on skill level.
        This makes the demo look sensible instead of random chaos with boots.
        """

        for session in sessions:
            participants = (
                Participation.objects
                .filter(session=session)
                .select_related("user", "user__profile")
                .order_by("user__username")
            )

            users = [p.user for p in participants]

            if len(users) < 8:
                continue

            sorted_users = sorted(
                users,
                key=lambda u: getattr(u.profile, "skill_level", 5),
                reverse=True,
            )

            team_a = []
            team_b = []
            team_a_skill = 0
            team_b_skill = 0

            for user in sorted_users:
                skill = getattr(user.profile, "skill_level", 5)

                if team_a_skill <= team_b_skill:
                    team_a.append(user)
                    team_a_skill += skill
                else:
                    team_b.append(user)
                    team_b_skill += skill

            for user in team_a:
                TeamAssignment.objects.create(
                    session=session,
                    user=user,
                    team="A",
                )

            for user in team_b:
                TeamAssignment.objects.create(
                    session=session,
                    user=user,
                    team="B",
                )

    def create_ratings(self, sessions):
        comments = [
            "Great communication and effort.",
            "Reliable player and worked well with the team.",
            "Good positioning throughout the match.",
            "Strong performance and positive attitude.",
            "Helpful team player with solid decision making.",
            "Good energy and fair play.",
            "Could improve communication but played well.",
            "Confident performance and good teamwork.",
        ]

        past_sessions = [
            session for session in sessions
            if session.start_datetime < timezone.now()
        ]

        random.seed(42)

        for session in past_sessions:
            attended_users = list(
                Participation.objects
                .filter(session=session, attended=True)
                .select_related("user")
                .values_list("user", flat=False)
            )

            attended_user_ids = [item[0] for item in attended_users]

            if len(attended_user_ids) < 2:
                continue

            User = get_user_model()
            users = list(User.objects.filter(id__in=attended_user_ids))

            # Create a few realistic ratings per past attended match.
            number_of_ratings = min(6, len(users))

            for _ in range(number_of_ratings):
                rater, ratee = random.sample(users, 2)

                Rating.objects.create(
                    session=session,
                    rater=rater,
                    ratee=ratee,
                    score=random.choice([3, 4, 4, 5, 5]),
                    comment=random.choice(comments),
                )