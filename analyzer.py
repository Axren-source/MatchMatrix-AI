def calculate_win_chances(home_stats, away_stats):
    # ⚡ NO DRAW BIAS - Start neutral
    home_chance = 35.0
    draw_chance = 30.0
    away_chance = 35.0

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

    # Draw only if truly close match
    closeness = abs(form_diff) + abs(goal_diff) + abs(defense_diff)
    
    if closeness < 1.5:
        draw_chance += 8
        home_chance -= 4
        away_chance -= 4
    elif closeness < 3:
        draw_chance += 3
        home_chance -= 1.5
        away_chance -= 1.5

    # Ensure minimum probability
    home_chance = max(home_chance, 10)
    draw_chance = max(draw_chance, 5)
    away_chance = max(away_chance, 10)

    # Normalize to 100%
    total = home_chance + draw_chance + away_chance
    home_chance = home_chance / total * 100
    draw_chance = draw_chance / total * 100
    away_chance = away_chance / total * 100

    return home_chance, draw_chance, away_chance


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