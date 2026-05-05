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
        return 90
    if any(word in name for word in query.split()):
        return 70
    return 0

TEAM_CACHE = []

def find_team_by_name(name: str):
    print(f"🔍 Searching API for: {name}")

    # 🔥 ALIASES (CRITICAL)
    ALIASES = {
        "psg": "Paris Saint-Germain",
        "paris": "Paris Saint-Germain",
        "bayern": "FC Bayern München",
        "atletico": "Atlético Madrid",
        "barca": "Barcelona",
        "man utd": "Manchester United",
        "man city": "Manchester City"
    }

    name = ALIASES.get(name.lower(), name)

    data = api_get("teams", {"name": name})

    if not data or not data.get("teams"):
        print("❌ No teams found from API")
        return None

    query = name.lower().replace("-", " ").replace(".", "")

    best = None
    best_score = 0

    for team in data["teams"]:
        team_name = team.get("name", "").lower().replace("-", " ").replace(".", "")

        score = 0

        # EXACT
        if query == team_name:
            score = 100

        # CONTAINS
        elif query in team_name:
            score = 90

        # WORD MATCH
        elif any(word in team_name for word in query.split()):
            score = 70

        if score > best_score:
            best_score = score
            best = team

    if not best:
        print("❌ No good match after scoring")
        return None

    print(f"✅ Best match: {best['name']}")

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
def compute_team_stats(matches, team_id=None):
    """
    Compute team statistics from matches.
    If team_id provided, calculates from team perspective (home/away).
    Otherwise calculates assuming first team in match is home team.
    """
    if not matches:
        return None

    form_points = 0
    goals_scored = 0
    goals_conceded = 0
    wins = 0
    draws = 0
    losses = 0
    clean_sheets = 0
    failed_to_score = 0

    total = len(matches)

    for m in matches:
        try:
            score = m.get("score", {}).get("fullTime", {})
            home_goals = score.get("home") or 0
            away_goals = score.get("away") or 0
            
            if home_goals is None or away_goals is None:
                continue

            # If team_id provided, calculate from team perspective
            if team_id:
                home_id = m.get("homeTeam", {}).get("id")
                away_id = m.get("awayTeam", {}).get("id")
                
                if team_id == home_id:
                    scored = home_goals
                    conceded = away_goals
                else:
                    scored = away_goals
                    conceded = home_goals
            else:
                # Default: treat as home team
                scored = home_goals
                conceded = away_goals

            goals_scored += scored
            goals_conceded += conceded

            if scored > conceded:
                form_points += 3
                wins += 1
            elif scored == conceded:
                form_points += 1
                draws += 1
            else:
                losses += 1

            if conceded == 0:
                clean_sheets += 1
            if scored == 0:
                failed_to_score += 1
        except Exception:
            continue

    return {
        "form_points": form_points / total if total > 0 else 0,
        "goals_scored_avg": goals_scored / total if total > 0 else 0,
        "goals_conceded_avg": goals_conceded / total if total > 0 else 0,
        "goal_diff_avg": (goals_scored - goals_conceded) / total if total > 0 else 0,
        "win_rate": wins / total if total > 0 else 0,
        "clean_sheet_rate": clean_sheets / total if total > 0 else 0,
        "failed_to_score_rate": failed_to_score / total if total > 0 else 0,
        "wins": wins,
        "draws": draws,
        "losses": losses
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
    params = {}

    if date_from:
        params["dateFrom"] = date_from
    if date_to:
        params["dateTo"] = date_to

    # 🔥 IMPORTANT: remove strict filter
    # params["status"] = "SCHEDULED"

    endpoint = f"competitions/{code}/matches" if code else "matches"

    data = await async_api_get(endpoint, params=params)

    if data and "matches" in data:
        return data["matches"]

    return []


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

async def async_find_match_in_competitions(home_name: str, away_name: str, date_from=None, date_to=None):
    """
    Search for a match across ALL competitions defined in config.
    Returns the match data with competition info if found.
    """
    from config import COMPETITIONS
    
    home_name_lower = home_name.lower()
    away_name_lower = away_name.lower()
    
    # Try to find match by searching all competitions
    for comp_code in COMPETITIONS.keys():
        try:
            params = {}
            if date_from:
                params["dateFrom"] = date_from
            if date_to:
                params["dateTo"] = date_to
            
            data = await async_api_get(f"competitions/{comp_code}/matches", params)
            
            if not data or "matches" not in data:
                continue
            
            matches = data.get("matches", [])
            for match in matches:
                home = match.get("homeTeam", {}).get("name", "").lower()
                away = match.get("awayTeam", {}).get("name", "").lower()
                
                # Flexible matching - check if names are contained or vice versa
                def name_match(a, b):
                    return a in b or b in a

                if name_match(home_name_lower, home) and name_match(away_name_lower, away):
                    return match, comp_code, COMPETITIONS[comp_code]
        except Exception as e:
            print(f"⚠️ Error searching {comp_code}: {e}")
            continue
    
    return None, None, None

def search_team_by_name(name: str):
    """Search for a team using football-data API"""
    print(f"🔍 Searching API for team: {name}")

    data = api_get("teams")

    if not data or "teams" not in data:
        print("❌ API returned no teams")
        return None

    name_lower = name.lower()

    for team in data["teams"]:
        team_name = team.get("name", "").lower()

        # Flexible matching
        if name_lower in team_name or team_name in name_lower:
            print(f"✅ Found: {team['name']} (ID: {team['id']})")
            return team

    print("❌ No match found in API")
    return None