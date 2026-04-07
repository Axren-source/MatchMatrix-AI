import json
import os
import time
import requests

from config import (
    API_KEY,
    BASE_URL,
    COMPETITIONS,
    CLUB_COMPETITIONS,
    INTERNATIONAL_COMPETITIONS,
)

HEADERS = {
    "X-Auth-Token": API_KEY
}

session = requests.Session()
session.headers.update(HEADERS)

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)


def api_get(url, params=None, retries=5):
    wait_time = 8

    for attempt in range(retries):
        response = session.get(url, params=params, timeout=30)

        if response.status_code == 429:
            print(f"Rate limit hit. Waiting {wait_time} seconds...")
            time.sleep(wait_time)
            wait_time *= 2
            continue

        response.raise_for_status()
        return response.json()

    raise Exception("Too many requests. Please wait and try again.")


def load_cache(filename):
    path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(filename, data):
    path = os.path.join(CACHE_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_name(name: str) -> str:
    return " ".join(name.lower().strip().split())


def get_teams_from_competition(code: str, use_cache=True):
    cache_name = f"teams_{code}.json"

    if use_cache:
        cached = load_cache(cache_name)
        if cached is not None:
            return cached

    url = f"{BASE_URL}/competitions/{code}/teams"
    data = api_get(url)
    teams = data.get("teams", [])

    save_cache(cache_name, teams)
    time.sleep(1.0)
    return teams


def get_all_teams_from_competitions(codes, use_cache=True):
    all_teams = {}
    team_sources = {}

    for code in codes:
        try:
            teams = get_teams_from_competition(code, use_cache=use_cache)
            for team in teams:
                team_id = team["id"]

                if team_id not in all_teams:
                    all_teams[team_id] = team
                    team_sources[team_id] = []

                team_sources[team_id].append(code)
        except Exception as e:
            print(f"Could not load teams for {code}: {e}")

    result = []
    for team_id, team in all_teams.items():
        team_copy = dict(team)
        team_copy["competition_codes"] = team_sources[team_id]
        team_copy["competition_names"] = [
            COMPETITIONS.get(code, code) for code in team_sources[team_id]
        ]
        result.append(team_copy)

    return result


def get_all_club_teams(use_cache=True):
    return get_all_teams_from_competitions(CLUB_COMPETITIONS, use_cache=use_cache)


def get_all_national_teams(use_cache=True):
    return get_all_teams_from_competitions(INTERNATIONAL_COMPETITIONS, use_cache=use_cache)


def find_team_by_name(team_name: str, teams):
    target = normalize_name(team_name)

    exact_match = None
    partial_matches = []

    for team in teams:
        possible_names = [
            team.get("name", ""),
            team.get("shortName", ""),
            team.get("tla", "")
        ]

        lowered = [normalize_name(name) for name in possible_names if name]

        if target in lowered:
            exact_match = team
            break

        if any(target in name for name in lowered):
            partial_matches.append(team)

    if exact_match:
        return exact_match

    if partial_matches:
        return partial_matches[0]

    return None


def find_national_team(team_name: str):
    teams = get_all_national_teams()
    return find_team_by_name(team_name, teams)


def find_club_team(team_name: str):
    teams = get_all_club_teams()
    return find_team_by_name(team_name, teams)


def get_recent_team_matches(team_id: int, limit: int = 10, use_cache=True):
    cache_name = f"matches_{team_id}_{limit}.json"

    if use_cache:
        cached = load_cache(cache_name)
        if cached is not None:
            return cached

    url = f"{BASE_URL}/teams/{team_id}/matches"
    params = {
        "status": "FINISHED",
        "limit": limit
    }

    data = api_get(url, params=params)
    matches = data.get("matches", [])

    save_cache(cache_name, matches)
    time.sleep(1.0)
    return matches


def collect_team_dataset(team_id: int, recent_limit: int = 20):
    matches = get_recent_team_matches(team_id, limit=recent_limit)

    if not matches:
        return None

    scored = 0
    conceded = 0
    wins = 0
    draws = 0
    losses = 0
    clean_sheets = 0
    failed_to_score = 0
    match_count = 0

    for match in matches:
        full_time = match.get("score", {}).get("fullTime", {})
        home_goals = full_time.get("home")
        away_goals = full_time.get("away")

        if home_goals is None or away_goals is None:
            continue

        home_id = match.get("homeTeam", {}).get("id")
        away_id = match.get("awayTeam", {}).get("id")

        if team_id == home_id:
            team_goals = home_goals
            opp_goals = away_goals
        elif team_id == away_id:
            team_goals = away_goals
            opp_goals = home_goals
        else:
            continue

        match_count += 1
        scored += team_goals
        conceded += opp_goals

        if opp_goals == 0:
            clean_sheets += 1

        if team_goals == 0:
            failed_to_score += 1

        if team_goals > opp_goals:
            wins += 1
        elif team_goals == opp_goals:
            draws += 1
        else:
            losses += 1

    if match_count == 0:
        return None

    return {
        "matches_used": match_count,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "form_points": wins * 3 + draws,
        "goals_scored_avg": scored / match_count,
        "goals_conceded_avg": conceded / match_count,
        "goal_diff_avg": (scored - conceded) / match_count,
        "win_rate": wins / match_count,
        "clean_sheet_rate": clean_sheets / match_count,
        "failed_to_score_rate": failed_to_score / match_count,
    }

def get_matches_from_competition(code: str, season=None, use_cache=True):
    """
    Get all finished matches from a competition.
    Some competitions do not support every season year.
    """
    cache_name = f"competition_matches_{code}_{season if season else 'current'}.json"

    if use_cache:
        cached = load_cache(cache_name)
        if cached is not None:
            return cached

    url = f"{BASE_URL}/competitions/{code}/matches"
    params = {
        "status": "FINISHED"
    }

    # Only apply season to league/club competitions
    if season is not None and code not in ["WC", "EC"]:
        params["season"] = season

    try:
        data = api_get(url, params=params)
        matches = data.get("matches", [])
    except requests.exceptions.HTTPError as e:
        print(f"Skipping {code}: {e}")
        return []

    save_cache(cache_name, matches)
    time.sleep(1.0)
    return matches


def get_team_stats_before_match(team_id: int, all_matches: list, match_date: str, lookback: int = 5):
    """
    Build team stats using only matches BEFORE the target match date.
    """
    previous_matches = []

    for match in all_matches:
        utc_date = match.get("utcDate", "")
        if utc_date >= match_date:
            continue

        home_id = match.get("homeTeam", {}).get("id")
        away_id = match.get("awayTeam", {}).get("id")

        if team_id == home_id or team_id == away_id:
            full_time = match.get("score", {}).get("fullTime", {})
            if full_time.get("home") is None or full_time.get("away") is None:
                continue
            previous_matches.append(match)

    previous_matches = sorted(
        previous_matches,
        key=lambda x: x.get("utcDate", ""),
        reverse=True
    )[:lookback]

    wins = 0
    draws = 0
    losses = 0
    goals_scored = 0
    goals_conceded = 0
    clean_sheets = 0
    failed_to_score = 0
    matches_used = 0

    for match in previous_matches:
        home_id = match["homeTeam"]["id"]
        away_id = match["awayTeam"]["id"]
        home_goals = match["score"]["fullTime"]["home"]
        away_goals = match["score"]["fullTime"]["away"]

        if team_id == home_id:
            scored = home_goals
            conceded = away_goals
        else:
            scored = away_goals
            conceded = home_goals

        matches_used += 1
        goals_scored += scored
        goals_conceded += conceded

        if conceded == 0:
            clean_sheets += 1

        if scored == 0:
            failed_to_score += 1

        if scored > conceded:
            wins += 1
        elif scored == conceded:
            draws += 1
        else:
            losses += 1

    if matches_used == 0:
        return None

    form_points = wins * 3 + draws
    goal_diff_avg = (goals_scored - goals_conceded) / matches_used
    win_rate = wins / matches_used
    clean_sheet_rate = clean_sheets / matches_used
    failed_to_score_rate = failed_to_score / matches_used

    return {
        "matches_used": matches_used,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "form_points": form_points,
        "goals_scored_avg": goals_scored / matches_used,
        "goals_conceded_avg": goals_conceded / matches_used,
        "goal_diff_avg": goal_diff_avg,
        "win_rate": win_rate,
        "clean_sheet_rate": clean_sheet_rate,
        "failed_to_score_rate": failed_to_score_rate,
    }

def get_scheduled_matches_from_competition(code: str, date_from=None, date_to=None):
    url = f"{BASE_URL}/competitions/{code}/matches"
    params = {
        "status": "SCHEDULED"
    }

    if date_from:
        params["dateFrom"] = date_from
    if date_to:
        params["dateTo"] = date_to

    data = api_get(url, params=params)
    return data.get("matches", [])

def find_scheduled_match(home_name: str, away_name: str, competition_codes, date_from=None, date_to=None):
    home_name = home_name.lower().strip()
    away_name = away_name.lower().strip()

    for code in competition_codes:
        try:
            matches = get_scheduled_matches_from_competition(code, date_from=date_from, date_to=date_to)

            for match in matches:
                home = match.get("homeTeam", {}).get("name", "").lower()
                away = match.get("awayTeam", {}).get("name", "").lower()

                if home_name in home and away_name in away:
                    return match

                if away_name in home and home_name in away:
                    return match
        except Exception:
            continue

    return None


def get_scheduled_matches_from_competition(code: str, date_from=None, date_to=None, use_cache=False):
    """
    Get scheduled matches from a competition.
    """
    url = f"{BASE_URL}/competitions/{code}/matches"
    params = {
        "status": "SCHEDULED"
    }

    if date_from:
        params["dateFrom"] = date_from
    if date_to:
        params["dateTo"] = date_to

    data = api_get(url, params=params)
    return data.get("matches", [])

def team_name_matches(search_name: str, actual_name: str) -> bool:
    search_name = normalize_name(search_name)
    actual_name = normalize_name(actual_name)
    return search_name in actual_name or actual_name in search_name

def find_scheduled_fixture(home_name: str, away_name: str, competition_codes, date_from=None, date_to=None):
    """
    Find a scheduled fixture by team names across competitions.
    """
    for code in competition_codes:
        try:
            matches = get_scheduled_matches_from_competition(
                code,
                date_from=date_from,
                date_to=date_to,
                use_cache=False
            )

            for match in matches:
                match_home = match.get("homeTeam", {}).get("name", "")
                match_away = match.get("awayTeam", {}).get("name", "")

                direct_match = (
                    team_name_matches(home_name, match_home)
                    and team_name_matches(away_name, match_away)
                )

                reverse_match = (
                    team_name_matches(home_name, match_away)
                    and team_name_matches(away_name, match_home)
                )

                if direct_match or reverse_match:
                    return match, code

        except Exception as e:
            print(f"Could not check scheduled matches for {code}: {e}")

    return None, None