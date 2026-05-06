from random import Random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from scheduling.models import (
    MatchSession,
    Participation,
    TeamAssignment,
    MatchResult,
    PlayerMatchStat,
)


class Command(BaseCommand):
    help = "Seed realistic match results and player match stats for completed demo sessions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing match results and player match stats before seeding.",
        )

    def handle(self, *args, **options):
        rng = Random(42)

        if options["clear"]:
            PlayerMatchStat.objects.all().delete()
            MatchResult.objects.all().delete()
            self.stdout.write(self.style.WARNING("Cleared existing match results and player stats."))

        completed_sessions = (
            MatchSession.objects
            .filter(start_datetime__lt=timezone.now())
            .annotate(joined_count=Count("participants"))
            .filter(joined_count__gte=2)
            .order_by("start_datetime")
        )

        if not completed_sessions.exists():
            self.stdout.write(self.style.WARNING("No completed sessions with at least 2 players found."))
            return

        seeded_count = 0

        for session in completed_sessions:
            with transaction.atomic():
                participants = list(
                    Participation.objects
                    .filter(session=session)
                    .select_related("user", "user__profile")
                    .order_by("user__username")
                )

                if len(participants) < 2:
                    continue

                self._ensure_team_assignments(session, participants)

                team_a_users = list(
                    TeamAssignment.objects
                    .filter(session=session, team=TeamAssignment.TEAM_A)
                    .select_related("user", "user__profile")
                    .order_by("user__username")
                    .values_list("user", flat=False)
                )

                team_b_users = list(
                    TeamAssignment.objects
                    .filter(session=session, team=TeamAssignment.TEAM_B)
                    .select_related("user", "user__profile")
                    .order_by("user__username")
                    .values_list("user", flat=False)
                )

                team_a_users = [
                    assignment.user
                    for assignment in TeamAssignment.objects
                    .filter(session=session, team=TeamAssignment.TEAM_A)
                    .select_related("user", "user__profile")
                    .order_by("user__username")
                ]

                team_b_users = [
                    assignment.user
                    for assignment in TeamAssignment.objects
                    .filter(session=session, team=TeamAssignment.TEAM_B)
                    .select_related("user", "user__profile")
                    .order_by("user__username")
                ]

                if not team_a_users or not team_b_users:
                    users = [participation.user for participation in participants]
                    team_a_users = users[::2]
                    team_b_users = users[1::2]

                scoreline = self._scoreline_for_session(session, rng)
                team_a_score = scoreline["team_a_score"]
                team_b_score = scoreline["team_b_score"]

                result, _created = MatchResult.objects.update_or_create(
                    session=session,
                    defaults={
                        "team_a_score": team_a_score,
                        "team_b_score": team_b_score,
                        "team_a_possession": scoreline["team_a_possession"],
                        "team_b_possession": scoreline["team_b_possession"],
                        "team_a_shots": scoreline["team_a_shots"],
                        "team_b_shots": scoreline["team_b_shots"],
                        "team_a_chances": scoreline["team_a_chances"],
                        "team_b_chances": scoreline["team_b_chances"],
                        "team_a_pass_accuracy": scoreline["team_a_pass_accuracy"],
                        "team_b_pass_accuracy": scoreline["team_b_pass_accuracy"],
                        "team_a_tackles": scoreline["team_a_tackles"],
                        "team_b_tackles": scoreline["team_b_tackles"],
                        "notes": "Seeded demo result for dissertation prototype.",
                    },
                )

                PlayerMatchStat.objects.filter(session=session).delete()

                team_a_stats = self._create_player_stats(
                    session=session,
                    users=team_a_users,
                    team_goals=team_a_score,
                    rng=rng,
                    team_label="A",
                )

                team_b_stats = self._create_player_stats(
                    session=session,
                    users=team_b_users,
                    team_goals=team_b_score,
                    rng=rng,
                    team_label="B",
                )

                all_stats = team_a_stats + team_b_stats

                if all_stats:
                    mvp_stat = sorted(
                        all_stats,
                        key=lambda stat: (float(stat.rating), stat.goals, stat.assists),
                        reverse=True,
                    )[0]

                    result.mvp = mvp_stat.user
                    result.save(update_fields=["mvp"])

                seeded_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Seeded result for {session.id}: {session.title} "
                        f"({team_a_score}-{team_b_score})"
                    )
                )

        self.stdout.write(self.style.SUCCESS(f"Done. Seeded {seeded_count} completed match result(s)."))

    def _ensure_team_assignments(self, session, participants):
        existing_assignments = TeamAssignment.objects.filter(session=session).exists()

        if existing_assignments:
            return

        players = []

        for participation in participants:
            players.append({
                "user": participation.user,
                "score": self._profile_score(participation.user),
            })

        players.sort(key=lambda item: item["score"], reverse=True)

        team_a_total = 0
        team_b_total = 0
        team_a = []
        team_b = []

        for player in players:
            if team_a_total <= team_b_total:
                team_a.append(player)
                team_a_total += player["score"]
            else:
                team_b.append(player)
                team_b_total += player["score"]

        for player in team_a:
            TeamAssignment.objects.create(
                session=session,
                user=player["user"],
                team=TeamAssignment.TEAM_A,
            )

        for player in team_b:
            TeamAssignment.objects.create(
                session=session,
                user=player["user"],
                team=TeamAssignment.TEAM_B,
            )

    def _profile_score(self, user):
        try:
            profile = user.profile
        except Exception:
            return 3

        skill = getattr(profile, "skill_level", 3) or 3
        fitness = getattr(profile, "fitness_level", 3) or 3

        experience_value = str(getattr(profile, "experience", "")).lower()
        experience_scores = {
            "beginner": 1,
            "intermediate": 3,
            "advanced": 5,
        }

        experience = experience_scores.get(experience_value, 1)

        return float(skill) + float(fitness) + float(experience)

    def _scoreline_for_session(self, session, rng):
        title = session.title.lower()

        if "everyone attended" in title:
            team_a_score = 4
            team_b_score = 3
        elif "mixed attendance" in title:
            team_a_score = 3
            team_b_score = 2
        elif "nobody attended" in title:
            team_a_score = 1
            team_b_score = 1
        elif "community cup" in title:
            team_a_score = 4
            team_b_score = 3
        else:
            team_a_score = rng.choice([2, 3, 4])
            team_b_score = rng.choice([1, 2, 3])

        team_a_possession = rng.choice([51, 52, 53, 54, 55, 56])
        team_b_possession = 100 - team_a_possession

        team_a_shots = max(team_a_score + 5, rng.randint(10, 18))
        team_b_shots = max(team_b_score + 5, rng.randint(8, 16))

        team_a_chances = max(team_a_score + 3, rng.randint(7, 13))
        team_b_chances = max(team_b_score + 3, rng.randint(6, 12))

        team_a_pass_accuracy = rng.randint(78, 88)
        team_b_pass_accuracy = rng.randint(74, 86)

        team_a_tackles = rng.randint(12, 20)
        team_b_tackles = rng.randint(11, 19)

        return {
            "team_a_score": team_a_score,
            "team_b_score": team_b_score,
            "team_a_possession": team_a_possession,
            "team_b_possession": team_b_possession,
            "team_a_shots": team_a_shots,
            "team_b_shots": team_b_shots,
            "team_a_chances": team_a_chances,
            "team_b_chances": team_b_chances,
            "team_a_pass_accuracy": team_a_pass_accuracy,
            "team_b_pass_accuracy": team_b_pass_accuracy,
            "team_a_tackles": team_a_tackles,
            "team_b_tackles": team_b_tackles,
        }

    def _create_player_stats(self, session, users, team_goals, rng, team_label):
        created_stats = []

        if not users:
            return created_stats

        goal_distribution = [0 for _ in users]

        for goal_number in range(team_goals):
            player_index = goal_number % len(users)
            goal_distribution[player_index] += 1

        for index, user in enumerate(users):
            goals = goal_distribution[index]

            if goals > 0:
                assists = rng.choice([0, 1])
                rating = round(rng.uniform(7.0, 8.4), 1)
            else:
                assists = rng.choice([0, 0, 1])
                rating = round(rng.uniform(6.2, 7.4), 1)

            stat = PlayerMatchStat.objects.create(
                session=session,
                user=user,
                goals=goals,
                assists=assists,
                rating=rating,
            )

            created_stats.append(stat)

        return created_stats