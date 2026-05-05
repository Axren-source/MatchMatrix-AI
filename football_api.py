import requests
import aiohttp
import asyncio
import time
from config import API_KEY

BASE_URL = "https://v3.football.api-sports.io/"

HEADERS = {
    "x-apisports-key": API_KEY
}

# =========================
# SYNC REQUEST
# =========================
def api_get(endpoint, params=None):
    try:
        res = requests.get(BASE_URL + endpoint, headers=HEADERS, params=params, timeout=10)
        if res.status_code != 200:
            print("API error:", res.status_code)
            return None
        return res.json()
    except Exception as e:
        print("Error:", e)
        return None

# =========================
# ASYNC REQUEST
# =========================
async def async_api_get(endpoint, params=None):
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(BASE_URL + endpoint, params=params) as res:
            if res.status != 200:
                return None
            return await res.json()

# =========================
# TEAM SEARCH (FIXED)
# =========================
def search_team_by_name(name):
    data = api_get("teams", {"search": name})

    if not data or not data.get("response"):
        return None

    team = data["response"][0]["team"]

    return {
        "id": team["id"],
        "name": team["name"]
    }

# =========================
# MATCHES BY DATE
# =========================
async def get_matches_by_date(date):
    data = await async_api_get("fixtures", {"date": date})

    if not data or not data.get("response"):
        return []

    matches = []

    for m in data["response"]:
        matches.append({
            "home": m["teams"]["home"]["name"],
            "away": m["teams"]["away"]["name"],
            "home_id": m["teams"]["home"]["id"],
            "away_id": m["teams"]["away"]["id"],
            "fixture_id": m["fixture"]["id"],
        })

    return matches

# =========================
# TEAM STATS (FIXED)
# =========================
def compute_team_stats(matches, team_id):
    if not matches:
        return None

    total = len(matches)

    goals_scored = 0
    goals_conceded = 0
    wins = 0
    form_points = 0

    for m in matches:
        home_id = m["teams"]["home"]["id"]
        away_id = m["teams"]["away"]["id"]

        home_goals = m["goals"]["home"] or 0
        away_goals = m["goals"]["away"] or 0

        if team_id == home_id:
            scored = home_goals
            conceded = away_goals
        else:
            scored = away_goals
            conceded = home_goals

        goals_scored += scored
        goals_conceded += conceded

        if scored > conceded:
            wins += 1
            form_points += 3
        elif scored == conceded:
            form_points += 1

    return {
        "form_points": form_points / total,
        "goals_scored_avg": goals_scored / total,
        "goals_conceded_avg": goals_conceded / total,
        "goal_diff_avg": (goals_scored - goals_conceded) / total,
        "win_rate": wins / total,
        "clean_sheet_rate": 0,
        "failed_to_score_rate": 0
    }

# =========================
# LAST MATCHES
# =========================
async def get_last_matches(team_id):
    data = await async_api_get("fixtures", {
        "team": team_id,
        "last": 5
    })

    if not data:
        return []

    return data.get("response", [])