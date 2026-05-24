def calculate_win_chances(home_stats, away_stats):
    # ⚡ NO DRAW BIAS - Draws heavily suppressed
    home_chance = 40.0
    draw_chance = 20.0  # Reduced from 30% to 20%
    away_chance = 40.0

    # Form points (recent performance)
    form_diff = home_stats["form_points"] - away_stats["form_points"]
    home_chance += form_diff * 2.5
    away_chance -= form_diff * 2.5

    # Goals scored difference (attacking power)
    goal_diff = home_stats["goals_scored_avg"] - away_stats["goals_scored_avg"]
    home_chance += goal_diff * 8.0
    away_chance -= goal_diff * 8.0

    # Defense quality (conceded average)
    defense_diff = away_stats["goals_conceded_avg"] - home_stats["goals_conceded_avg"]
    home_chance += defense_diff * 7.0
    away_chance -= defense_diff * 7.0

    # Head-to-head advantage (if available)
    if "h2h_advantage" in home_stats and "h2h_advantage" in away_stats:
        h2h_diff = home_stats["h2h_advantage"] - away_stats["h2h_advantage"]
        home_chance += h2h_diff * 3.0
        away_chance -= h2h_diff * 3.0

    # Recent form emphasis (last 5 matches)
    if "recent_form" in home_stats:
        recent_diff = home_stats["recent_form"] - away_stats["recent_form"]
        home_chance += recent_diff * 5.0
        away_chance -= recent_diff * 5.0

    # Win rate emphasis
    home_chance += (home_stats["win_rate"] - away_stats["win_rate"]) * 20.0

    # Draw only if EXTREMELY close match
    closeness = abs(form_diff) + abs(goal_diff) + abs(defense_diff)
    
    if closeness < 0.5:  # Almost never
        draw_chance += 3
        home_chance -= 1.5
        away_chance -= 1.5
    elif closeness < 1.0:
        draw_chance += 1
        home_chance -= 0.5
        away_chance -= 0.5

    # Ensure minimum probability (draws capped very low)
    home_chance = max(home_chance, 15)
    draw_chance = max(draw_chance, 2)  # Only 2% minimum for draws
    away_chance = max(away_chance, 15)

    # Normalize to 100%
    total = home_chance + draw_chance + away_chance
    home_chance = home_chance / total * 100
    draw_chance = draw_chance / total * 100
    away_chance = away_chance / total * 100

    return home_chance, draw_chance, away_chance


def _stat(stats, key, default=0):
    return stats.get(key, default)


def _clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def _legacy_calculate_win_chances(home_stats, away_stats):
    home_chance = 40.0
    draw_chance = 22.0
    away_chance = 38.0

    form_diff = _stat(home_stats, "weighted_form", home_stats["form_points"]) - _stat(away_stats, "weighted_form", away_stats["form_points"])
    goal_diff = home_stats["goals_scored_avg"] - away_stats["goals_scored_avg"]
    defense_diff = away_stats["goals_conceded_avg"] - home_stats["goals_conceded_avg"]
    momentum_diff = _stat(home_stats, "momentum") - _stat(away_stats, "momentum")

    home_chance += form_diff * 3.0
    away_chance -= form_diff * 3.0

    home_chance += goal_diff * 8.0
    away_chance -= goal_diff * 8.0

    home_chance += defense_diff * 7.0
    away_chance -= defense_diff * 7.0

    home_chance += momentum_diff * 4.0
    away_chance -= momentum_diff * 4.0

    home_chance += _stat(home_stats, "home_advantage_rating") * 4.0
    home_chance += _stat(away_stats, "away_weakness_rating") * 3.0

    if "h2h_advantage" in home_stats and "h2h_advantage" in away_stats:
        h2h_diff = home_stats["h2h_advantage"] - away_stats["h2h_advantage"]
        home_chance += h2h_diff * 3.0
        away_chance -= h2h_diff * 3.0

    if "recent_form" in home_stats:
        recent_diff = home_stats["recent_form"] - away_stats["recent_form"]
        home_chance += recent_diff * 4.5
        away_chance -= recent_diff * 4.5

    home_chance += (home_stats["win_rate"] - away_stats["win_rate"]) * 18.0

    closeness = abs(form_diff) + abs(goal_diff) + abs(defense_diff) + abs(momentum_diff)
    attacking_load = home_stats["goals_scored_avg"] + away_stats["goals_scored_avg"]
    volatility = (_stat(home_stats, "goal_volatility") + _stat(away_stats, "goal_volatility")) / 2

    if closeness < 0.8 and attacking_load <= 2.4:
        draw_chance += 7
        home_chance -= 3.5
        away_chance -= 3.5
    elif closeness < 1.4:
        draw_chance += 3
        home_chance -= 1.5
        away_chance -= 1.5

    if attacking_load >= 2.8:
        draw_chance -= 5
    if volatility >= 1.4:
        draw_chance -= 4

    home_chance = max(home_chance, 15)
    draw_chance = _clamp(draw_chance, 7, 31)
    away_chance = max(away_chance, 15)

    total = home_chance + draw_chance + away_chance
    return (
        home_chance / total * 100,
        draw_chance / total * 100,
        away_chance / total * 100,
    )


def format_analysis(home_name, home_stats, away_name, away_stats):
    home_chance, draw_chance, away_chance = calculate_win_chances(home_stats, away_stats)

    if home_chance > draw_chance and home_chance > away_chance:
        verdict = f"Most likely: {home_name} win"
    elif away_chance > draw_chance and away_chance > home_chance:
        verdict = f"Most likely: {away_name} win"
    else:
        verdict = "Most likely: Draw"

    return f"""
{home_name}
- Form points: {home_stats['form_points']}
- Record: {home_stats['wins']}W {home_stats['draws']}D {home_stats['losses']}L
- Avg goals scored: {home_stats['goals_scored_avg']:.2f}
- Avg goals conceded: {home_stats['goals_conceded_avg']:.2f}

{away_name}
- Form points: {away_stats['form_points']}
- Record: {away_stats['wins']}W {away_stats['draws']}D {away_stats['losses']}L
- Avg goals scored: {away_stats['goals_scored_avg']:.2f}
- Avg goals conceded: {away_stats['goals_conceded_avg']:.2f}

Win Chances:
- {home_name}: {home_chance:.1f}%
- Draw: {draw_chance:.1f}%
- {away_name}: {away_chance:.1f}%

{verdict}
""".strip()
