from django.db.models import Avg


def peer_rating_score(user):
    from .models import Rating

    average = Rating.objects.filter(ratee=user).aggregate(
        average_score=Avg("score")
    )["average_score"]

    if average is None:
        return 0

    return round(float(average), 2)


def attendance_reliability_score(user):
    from .models import Participation

    participations = Participation.objects.filter(user=user)
    total = participations.count()

    if total == 0:
        return 0

    attended = participations.filter(attended=True).count()
    return round((attended / total) * 5, 2)


def calculate_player_strength(user):
    try:
        profile = user.profile
    except Exception:
        return 0

    experience_scores = {
        "beginner": 1,
        "intermediate": 2,
        "advanced": 3,
    }

    skill = getattr(profile, "skill_level", 0)
    fitness = getattr(profile, "fitness_level", 0)

    experience = experience_scores.get(
        str(getattr(profile, "experience", "")).lower(),
        1
    )

    peer_score = peer_rating_score(user)
    reliability_score = attendance_reliability_score(user)

    strength = (skill * 2) + fitness + experience + peer_score + reliability_score

    return round(strength, 2)


def allocate_teams_ml(users):
    player_scores = []

    for user in users:
        strength = calculate_player_strength(user)
        player_scores.append((user, strength))

    player_scores.sort(key=lambda item: item[1], reverse=True)

    team_a = []
    team_b = []
    team_a_total = 0
    team_b_total = 0

    for user, strength in player_scores:
        if team_a_total <= team_b_total:
            team_a.append(user)
            team_a_total += strength
        else:
            team_b.append(user)
            team_b_total += strength

    return {
        "team_a": team_a,
        "team_b": team_b,
        "team_a_total": round(team_a_total, 2),
        "team_b_total": round(team_b_total, 2),
        "difference": round(abs(team_a_total - team_b_total), 2),
    }