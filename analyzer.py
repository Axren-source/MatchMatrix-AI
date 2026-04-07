def calculate_win_chances(home_stats, away_stats):
    home_chance = 33.0
    draw_chance = 34.0
    away_chance = 33.0

    form_diff = home_stats["form_points"] - away_stats["form_points"]
    goal_diff = home_stats["goals_scored_avg"] - away_stats["goals_scored_avg"]
    defense_diff = away_stats["goals_conceded_avg"] - home_stats["goals_conceded_avg"]

    home_chance += form_diff * 1.0
    away_chance -= form_diff * 1.0

    home_chance += goal_diff * 7.0
    away_chance -= goal_diff * 7.0

    home_chance += defense_diff * 6.0
    away_chance -= defense_diff * 6.0

    closeness = abs(form_diff) + abs(goal_diff) + abs(defense_diff)

    if closeness < 3:
        draw_chance += 10
        home_chance -= 5
        away_chance -= 5
    elif closeness < 6:
        draw_chance += 5
        home_chance -= 2.5
        away_chance -= 2.5

    home_chance = max(home_chance, 5)
    draw_chance = max(draw_chance, 5)
    away_chance = max(away_chance, 5)

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