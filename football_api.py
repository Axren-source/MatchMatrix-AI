import requests
import aiohttp
import asyncio
import time
from config import API_KEY, BASE_URL
import json
import os

# =========================
# CACHE SYSTEM
# =========================
CACHE = {}
CACHE_TTL = 300  # seconds


# =========================
# CORE HTTP FUNCTIONS
# =========================
def api_get(endpoint, params=None):
    url = f"{BASE_URL}{endpoint.lstrip('/')}"
    headers = {"X-Auth-Token": API_KEY}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code == 429:
            print("⚠️ Rate limit hit. Waiting...")
            time.sleep(60)
            return api_get(endpoint, params)

        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}")
            return None

        return response.json()

    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None


async def async_api_get(endpoint, params=None, retries=3):
    key = f"{endpoint}-{params}"

    # CACHE HIT
    if key in CACHE:
        data, ts = CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return data

    url = f"{BASE_URL}{endpoint.lstrip('/')}"
    headers = {"X-Auth-Token": API_KEY}

    async with aiohttp.ClientSession(headers=headers) as session:
        for _ in range(retries):
            try:
                async with session.get(url, params=params, timeout=20) as response:
                    if response.status == 429:
                        await asyncio.sleep(60)
                        continue

                    if response.status != 200:
                        return None

                    data = await response.json()

                    # SAVE CACHE
                    CACHE[key] = (data, time.time())

                    return data

            except Exception:
                await asyncio.sleep(2)

    return None

def score_match(query, team_name):
    query = query.lower()
    name = team_name.lower()

    if query == name:
        return 100
    if query in name:
        return 70
    if name.startswith(query):
        return 80
    return 0

def find_team_by_name(name: str):
    params = {"name": name}
    data = api_get("teams", params)

    if not data or not data.get("teams"):
        return None

    teams = data["teams"]

    # 🔥 pick best match instead of first
    best = max(teams, key=lambda t: score_match(name, t.get("name", "")))

    return {
        "id": best.get("id"),
        "name": best.get("name"),
        "shortName": best.get("shortName"),
        "tla": best.get("tla"),
        "country": best.get("area", {}).get("name", ""),
        "crest": best.get("crest")
    }

# =========================
# TEAM STATS ENGINE (🔥 CORE LOGIC)
# =========================
def compute_team_stats(matches, team_id):
    if not matches:
        return None

    form_points = 0
    goals_scored = 0
    goals_conceded = 0
    wins = 0
    clean_sheets = 0
    failed_to_score = 0

    total = len(matches)

    for m in matches:
        home_id = m["homeTeam"]["id"]
        away_id = m["awayTeam"]["id"]

        home_goals = m["score"]["fullTime"]["home"] or 0
        away_goals = m["score"]["fullTime"]["away"] or 0

        if team_id == home_id:
            scored = home_goals
            conceded = away_goals
        else:
            scored = away_goals
            conceded = home_goals

        goals_scored += scored
        goals_conceded += conceded

        if scored > conceded:
            form_points += 3
            wins += 1
        elif scored == conceded:
            form_points += 1

        if conceded == 0:
            clean_sheets += 1
        if scored == 0:
            failed_to_score += 1

    return {
        "form_points": form_points / total,
        "goals_scored_avg": goals_scored / total,
        "goals_conceded_avg": goals_conceded / total,
        "goal_diff_avg": (goals_scored - goals_conceded) / total,
        "win_rate": wins / total,
        "clean_sheet_rate": clean_sheets / total,
        "failed_to_score_rate": failed_to_score / total
    }


# =========================
# DATA COLLECTION
# =========================
async def async_collect_team_dataset(team_id: int, limit: int = 5):
    params = {"status": "FINISHED", "limit": limit}

    data = await async_api_get(f"teams/{team_id}/matches", params)

    if not data or "matches" not in data:
        return None

    return compute_team_stats(data["matches"], team_id)


def collect_team_dataset(team_id: int, limit: int = 5):
    params = {"status": "FINISHED", "limit": limit}

    data = api_get(f"teams/{team_id}/matches", params)

    if not data or "matches" not in data:
        return None

    return compute_team_stats(data["matches"], team_id)


# =========================
# MATCH INTENSITY
# =========================
def compute_match_intensity(matches):
    if not matches:
        return 0

    high_scoring = 0

    for m in matches:
        total_goals = (
            (m["score"]["fullTime"]["home"] or 0) +
            (m["score"]["fullTime"]["away"] or 0)
        )

        if total_goals >= 3:
            high_scoring += 1

    return high_scoring / len(matches)


# =========================
# SCHEDULED MATCHES
# =========================
async def async_get_scheduled_matches_from_competition(code=None, date_from=None, date_to=None):
    params = {"status": "SCHEDULED"}

    if date_from:
        params["dateFrom"] = date_from
    if date_to:
        params["dateTo"] = date_to

    endpoint = f"competitions/{code}/matches" if code else "matches"

    data = await async_api_get(endpoint, params)

    if not data or "matches" not in data:
        return []

    return data["matches"]


# =========================
# TEAM DATABASE
# =========================


def normalize_name(name: str):
    return " ".join(name.lower().strip().split())


def normalize_team_object(team: dict):
    return {
        "id": team.get("id"),
        "name": team.get("name"),
        "shortName": team.get("shortName"),
        "tla": team.get("tla"),
        "country": team.get("area", {}).get("name", ""),
        "crest": team.get("crest")
    }

def find_club_team(name: str):
    return find_team_by_name(name)

def find_national_team(name: str):
    return find_team_by_name(name)