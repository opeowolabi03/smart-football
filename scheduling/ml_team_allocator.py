from math import ceil

from django.db.models import Avg

from .models import Participation, Rating


try:
    import pandas as pd
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    ML_AVAILABLE = True
except Exception:
    pd = None
    KMeans = None
    StandardScaler = None
    ML_AVAILABLE = False


def _clamp_number(value, minimum, maximum, default=0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = default

    return max(minimum, min(value, maximum))


def _normalise_profile_rating(value):
    """
    Supports both old 1-10 profile data and newer 1-5 profile data.
    If the value is above 5, treat it as old 1-10 data and convert it.
    """
    value = _clamp_number(value, 1, 10, default=3)

    if value > 5:
        value = value / 2

    return _clamp_number(value, 1, 5, default=3)


def _experience_score(profile):
    if not profile:
        return 1.0

    experience_value = str(getattr(profile, "experience", "")).lower()

    experience_scores = {
        "beginner": 1.0,
        "intermediate": 3.0,
        "advanced": 5.0,
    }

    return experience_scores.get(experience_value, 1.0)


def _position_features(profile):
    position = "ANY"

    if profile:
        position = str(getattr(profile, "position_preference", "ANY")).upper()

    return {
        "position_gk": 1 if position == "GK" else 0,
        "position_def": 1 if position == "DEF" else 0,
        "position_mid": 1 if position == "MID" else 0,
        "position_fwd": 1 if position == "FWD" else 0,
        "position_any": 1 if position == "ANY" else 0,
    }


def peer_rating_score(user):
    """
    Average score this player has received from peer ratings.
    Neutral default is 3/5 if they have no ratings yet.
    """
    average_rating = Rating.objects.filter(ratee=user).aggregate(
        average=Avg("score")
    )["average"]

    if average_rating is None:
        return 3.0

    return _clamp_number(average_rating, 1, 5, default=3)


def attendance_reliability_score(user):
    """
    Turns attendance history into a 1-5 score.
    If a player has no attendance history, use neutral 3/5.
    """
    participations = Participation.objects.filter(user=user)

    total = participations.count()

    if total == 0:
        return 3.0

    attended = participations.filter(attended=True).count()
    rate = attended / total

    return round(max(1.0, rate * 5), 2)


def calculate_player_strength(user):
    """
    Final explainable strength score used by the allocator.

    It combines:
    - skill
    - fitness
    - experience
    - peer ratings
    - attendance reliability
    """
    try:
        profile = user.profile
    except Exception:
        profile = None

    if not profile:
        return 3.0

    skill = _normalise_profile_rating(getattr(profile, "skill_level", 3))
    fitness = _normalise_profile_rating(getattr(profile, "fitness_level", 3))
    experience = _experience_score(profile)
    peer_rating = peer_rating_score(user)
    reliability = attendance_reliability_score(user)

    strength = (
        (skill * 0.30)
        + (fitness * 0.20)
        + (experience * 0.15)
        + (peer_rating * 0.25)
        + (reliability * 0.10)
    )

    return round(strength, 2)


def _build_player_rows(participations):
    rows = []

    for participation in participations:
        user = participation.user

        try:
            profile = user.profile
        except Exception:
            profile = None

        skill = _normalise_profile_rating(getattr(profile, "skill_level", 3))
        fitness = _normalise_profile_rating(getattr(profile, "fitness_level", 3))
        experience = _experience_score(profile)
        peer_rating = peer_rating_score(user)
        reliability = attendance_reliability_score(user)
        position_data = _position_features(profile)

        strength = calculate_player_strength(user)

        row = {
            "user": user,
            "username": user.username,
            "skill": skill,
            "fitness": fitness,
            "experience": experience,
            "peer_rating": peer_rating,
            "reliability": reliability,
            "strength": strength,
        }

        row.update(position_data)
        rows.append(row)

    return rows


def _fairness_score(team_a_total, team_b_total):
    highest_total = max(team_a_total, team_b_total, 1)
    difference = abs(team_a_total - team_b_total)

    score = 100 - ((difference / highest_total) * 100)

    return round(max(0, min(score, 100)))


def _fairness_label(score):
    if score >= 90:
        return "Excellent"

    if score >= 75:
        return "Good"

    if score >= 60:
        return "Fair"

    return "Needs review"


def _allocate_balanced(player_rows, used_ml=False, ml_reason="Fallback balancing used."):
    """
    Safe greedy allocator.
    This is used both as fallback and after ML clustering.
    """
    total_players = len(player_rows)

    target_a = ceil(total_players / 2)
    target_b = total_players // 2

    team_a = []
    team_b = []

    team_a_total = 0.0
    team_b_total = 0.0

    for player in player_rows:
        if len(team_a) >= target_a:
            team_b.append(player)
            team_b_total += player["strength"]
        elif len(team_b) >= target_b:
            team_a.append(player)
            team_a_total += player["strength"]
        elif team_a_total <= team_b_total:
            team_a.append(player)
            team_a_total += player["strength"]
        else:
            team_b.append(player)
            team_b_total += player["strength"]

    fairness = _fairness_score(team_a_total, team_b_total)

    return {
        "team_a": team_a,
        "team_b": team_b,
        "team_a_total": round(team_a_total, 2),
        "team_b_total": round(team_b_total, 2),
        "team_difference": round(abs(team_a_total - team_b_total), 2),
        "fairness_score": fairness,
        "fairness_label": _fairness_label(fairness),
        "used_ml": used_ml,
        "ml_reason": ml_reason,
    }


def allocate_teams_ml(participations):
    """
    ML-assisted team allocation.

    Uses KMeans clustering to group similar players by:
    - skill
    - fitness
    - experience
    - peer rating
    - attendance reliability
    - preferred position

    Then it distributes players into two balanced teams.
    If ML is unavailable or unsuitable, it safely falls back.
    """
    player_rows = _build_player_rows(participations)

    if len(player_rows) < 2:
        return _allocate_balanced(
            player_rows,
            used_ml=False,
            ml_reason="At least 2 players are needed."
        )

    if not ML_AVAILABLE:
        ordered_players = sorted(
            player_rows,
            key=lambda player: player["strength"],
            reverse=True
        )

        return _allocate_balanced(
            ordered_players,
            used_ml=False,
            ml_reason="scikit-learn or pandas is not installed, so fallback balancing was used."
        )

    if len(player_rows) < 4:
        ordered_players = sorted(
            player_rows,
            key=lambda player: player["strength"],
            reverse=True
        )

        return _allocate_balanced(
            ordered_players,
            used_ml=False,
            ml_reason="Not enough players for useful clustering, so fallback balancing was used."
        )

    df = pd.DataFrame(player_rows)

    feature_columns = [
        "skill",
        "fitness",
        "experience",
        "peer_rating",
        "reliability",
        "position_gk",
        "position_def",
        "position_mid",
        "position_fwd",
        "position_any",
    ]

    cluster_count = 2

    try:
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(df[feature_columns])

        kmeans = KMeans(
            n_clusters=cluster_count,
            random_state=42,
            n_init=10,
        )

        df["cluster"] = kmeans.fit_predict(scaled_features)

        clustered_players = []

        for cluster_id in sorted(df["cluster"].unique()):
            cluster_rows = (
                df[df["cluster"] == cluster_id]
                .sort_values("strength", ascending=False)
                .to_dict("records")
            )

            clustered_players.extend(cluster_rows)

        return _allocate_balanced(
            clustered_players,
            used_ml=True,
            ml_reason="KMeans clustering used player profile, peer rating, reliability, and position data."
        )

    except Exception as error:
        ordered_players = sorted(
            player_rows,
            key=lambda player: player["strength"],
            reverse=True
        )

        return _allocate_balanced(
            ordered_players,
            used_ml=False,
            ml_reason=f"ML failed safely, fallback balancing was used: {error}"
        )