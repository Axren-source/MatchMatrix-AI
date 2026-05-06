from datetime import datetime

import requests
import aiohttp
import asyncio
import time
from config import API_KEY, BASE_URL, CLUB_COMPETITIONS, FAST_COMPETITIONS, HEADERS, COMPETITIONS, INTERNATIONAL_COMPETITIONS

# =========================
# CACHE SYSTEM
# =========================
CACHE = {}
CACHE_TTL = 300  # seconds


def get_current_season():
    now = datetime.now()

    # football season rollover
    if now.month >= 7:
        return now.year

    return now.year - 1

# =========================
# CORE HTTP FUNCTIONS
# =========================
def api_get(endpoint, params=None):
    url = f"{BASE_URL}{endpoint.lstrip('/')}"
    headers = HEADERS
    clear_expired_cache()

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
    clear_expired_cache()

    # CACHE HIT
    if key in CACHE:
        data, ts = CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return data

    url = f"{BASE_URL}{endpoint.lstrip('/')}"
    headers = HEADERS

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
ALIASES = {
    "atletico": "Atletico Madrid",
    "atleti": "Atletico Madrid",
    "man utd": "Manchester United",
    "utd": "Manchester United",
    "man united": "Manchester United",
    "man city": "Manchester City",
    "city": "Manchester City",
    "psg": "Paris Saint Germain",
    "barca": "Barcelona",
    "bayern": "Bayern Munich",
    "inter": "Inter",
    "milan": "AC Milan",
    "juve": "Juventus",
    "dortmund": "Borussia Dortmund",
    "spurs": "Tottenham",
    "paris sg": "Paris Saint Germain",
    "ath madrid": "Atletico Madrid",
    "atm": "Atletico Madrid",
    "newcastle utd": "Newcastle",
    "sporting": "Sporting CP",
    "benfica": "Benfica",
}

def load_all_teams():
    global TEAM_CACHE

    if TEAM_CACHE:
        return TEAM_CACHE

    print("🔥 Loading teams database...")

    all_teams = []
    seen_ids = set()

    for league_id in CLUB_COMPETITIONS + INTERNATIONAL_COMPETITIONS:
        data = api_get(
            "teams",
            {
                "league": league_id,
                "season": get_current_season()
            }
        )

        if not data or "response" not in data:
            print(f"❌ Failed loading league {league_id}")
            continue

        for item in data["response"]:
            team = item.get("team", {})

            team_id = team.get("id")

            if team_id in seen_ids:
                continue

            seen_ids.add(team_id)

            all_teams.append(team)

    TEAM_CACHE = all_teams

    print(f"✅ Loaded {len(TEAM_CACHE)} teams")

    return TEAM_CACHE


def find_team_by_name(name: str):
    teams = load_all_teams()

    name = ALIASES.get(name.lower(), name)
    name = name.lower()

    best_match = None
    best_score = 0

    for team in teams:
        team_name = team.get("name", "").lower()

        score = 0

        if name == team_name:
            score = 100

        elif name in team_name:
            score = 90

        elif any(word in team_name for word in name.split()):
            score = 75

        if team_name.startswith(name):
            score += 10

        if score > best_score:
            best_score = score
            best_match = team

    if best_match:
        print(f"✅ Found: {best_match['name']}")

        return {
            "id": best_match.get("id"),
            "name": best_match.get("name"),
            "shortName": best_match.get("name"),
            "tla": best_match.get("code"),
            "country": best_match.get("country", ""),
            "crest": best_match.get("logo")
        }

    print("❌ No match found")
    return None

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
    data = await async_api_get(
        "fixtures",
        {
            "team": team_id,
            "last": limit
        }
    )

    if not data or "response" not in data:
        return None

    matches = []

    for m in data["response"]:
        matches.append({
            "homeTeam": {
                "id": m["teams"]["home"]["id"],
                "name": m["teams"]["home"]["name"]
            },
            "awayTeam": {
                "id": m["teams"]["away"]["id"],
                "name": m["teams"]["away"]["name"]
            },
            "score": {
                "fullTime": {
                    "home": m["goals"]["home"],
                    "away": m["goals"]["away"]
                }
            }
        })

    return compute_team_stats(matches, team_id)


def collect_team_dataset(team_id: int, limit: int = 5):
    data = api_get(
        "fixtures",
        {
            "team": team_id,
            "last": limit
        }
    )

    if not data or "response" not in data:
        return None

    matches = []

    for m in data["response"]:
        matches.append({
            "homeTeam": {
                "id": m["teams"]["home"]["id"],
                "name": m["teams"]["home"]["name"]
            },
            "awayTeam": {
                "id": m["teams"]["away"]["id"],
                "name": m["teams"]["away"]["name"]
            },
            "score": {
                "fullTime": {
                    "home": m["goals"]["home"],
                    "away": m["goals"]["away"]
                }
            }
        })

    return compute_team_stats(matches, team_id)

async def get_last_matches(team_id, limit=5):
    data = await async_api_get(
        "fixtures",
        {
            "team": team_id,
            "last": limit
        }
    )

    if not data or "response" not in data:
        return []

    matches = []

    for m in data["response"]:
        matches.append({
            "homeTeam": {
                "id": m["teams"]["home"]["id"],
                "name": m["teams"]["home"]["name"]
            },
            "awayTeam": {
                "id": m["teams"]["away"]["id"],
                "name": m["teams"]["away"]["name"]
            },
            "score": {
                "fullTime": {
                    "home": m["goals"]["home"],
                    "away": m["goals"]["away"]
                }
            }
        })

    return matches

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

    if code:
        params["league"] = code

    if date_from:
        params["date"] = date_from

    params["season"] = get_current_season()
    params["timezone"] = "Asia/Bangkok"

    data = await async_api_get("fixtures", params)

    if not data or "response" not in data:
        return []

    matches = []

    for m in data["response"]:
        matches.append({
            "homeTeam": {
                "name": m["teams"]["home"]["name"]
            },
            "awayTeam": {
                "name": m["teams"]["away"]["name"]
            },
            "utcDate": m["fixture"]["date"],
            "competition": {
                "name": m["league"]["name"]
            }
        })

    return matches


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
        "country": team.get("country", ""),
        "crest": team.get("crest")
    }

def find_club_team(name: str):
    return find_team_by_name(name)

def find_national_team(name: str):
    return find_team_by_name(name)

async def async_find_match_in_competitions(home_name: str, away_name: str, date_from=None, date_to=None):

    home_name_lower = home_name.lower()
    away_name_lower = away_name.lower()

    for league_id in COMPETITIONS.keys():

        params = {
            "league": league_id,
            "season": get_current_season(),
            "timezone": "Asia/Bangkok"
        }

        if date_from:
            params["date"] = date_from

        data = await async_api_get("fixtures", params)

        if not data or "response" not in data:
            continue

        for m in data["response"]:

            home = m["teams"]["home"]["name"].lower()
            away = m["teams"]["away"]["name"].lower()

            def match_name(a, b):
                return a in b or b in a

            if match_name(home_name_lower, home) and match_name(away_name_lower, away):
                return (
                    m,
                    league_id,
                    COMPETITIONS[league_id]
                )

    return None, None, None

def clear_expired_cache():
    now = time.time()

    expired = []

    for key, (_, ts) in CACHE.items():
        if now - ts > CACHE_TTL:
            expired.append(key)

    for key in expired:
        del CACHE[key]