from datetime import datetime, timedelta


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

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=30
        )

        if response.status_code == 429:
            print("⚠️ Rate limit hit.")
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

    async with aiohttp.ClientSession(headers=HEADERS) as session:
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
    "man utd": "Manchester United",
    "utd": "Manchester United",
    "man united": "Manchester United",
    "man city": "Manchester City",
    "city": "Manchester City",
    "paris sg": "Paris Saint-Germain",
    "barca": "Barcelona",
    "inter": "Inter",
    "milan": "AC Milan",
    "juve": "Juventus",
    "dortmund": "Borussia Dortmund",
    "spurs": "Tottenham",
    "psg": "Paris Saint-Germain",
    "ath madrid": "Atletico Madrid",
    "atm": "Atletico Madrid",
    "newcastle utd": "Newcastle",
    "sporting": "Sporting CP",
    "benfica": "Benfica",
    "atletico madrid": "Club Atlético de Madrid",
    "bayern munich": "FC Bayern München",
}

def load_all_teams():
    global TEAM_CACHE

    if TEAM_CACHE:
        return TEAM_CACHE

    print("🔥 Loading teams database...")

    all_teams = []
    seen_ids = set()
    league_ids = list(set(CLUB_COMPETITIONS + INTERNATIONAL_COMPETITIONS))

    for league_id in league_ids:
        data = api_get(
            f"competitions/{league_id}/teams"
        )

        if not data or "teams" not in data:
            print(f"❌ Failed loading league {league_id}")
            continue

        for team in data["teams"]:

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

        elif any(word == part for part in team_name.split() for word in name.split()):
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
            "shortName": best_match.get("shortName"),
            "tla": best_match.get("tla"),
            "country": best_match.get("area", {}).get("name", ""),
            "crest": best_match.get("crest")
        }

    print("❌ No match found")
    return None

# =========================
# TEAM STATS ENGINE (🔥 CORE LOGIC)
# =========================
def compute_team_stats(matches, team_id=None):

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

    valid_matches = 0

    for m in matches:

        try:
            score = m.get("score", {}).get("fullTime", {})

            home_goals = score.get("home")
            away_goals = score.get("away")

            if home_goals is None or away_goals is None:
                continue

            valid_matches += 1

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

    if valid_matches == 0:
        return None

    return {
        "form_points": form_points / valid_matches,
        "goals_scored_avg": goals_scored / valid_matches,
        "goals_conceded_avg": goals_conceded / valid_matches,
        "goal_diff_avg": (goals_scored - goals_conceded) / valid_matches,
        "win_rate": wins / valid_matches,
        "clean_sheet_rate": clean_sheets / valid_matches,
        "failed_to_score_rate": failed_to_score / valid_matches,
        "wins": wins,
        "draws": draws,
        "losses": losses
    }


# =========================
# DATA COLLECTION
# =========================
async def async_collect_team_dataset(team_id: int, limit: int = 5):
    data = await async_api_get(
        f"teams/{team_id}/matches",
        {
            "limit": limit
        }
    )

    if not data or "matches" not in data:
        return None

    matches = []
    matches_data = data["matches"][:limit]

    for m in matches_data:
        matches.append({
            "homeTeam": {
                "id": m["homeTeam"]["id"],
                "name": m["homeTeam"]["name"]
            },
            "awayTeam": {
                "id": m["awayTeam"]["id"],
                "name": m["awayTeam"]["name"]
            },
            "score": {
                "fullTime": {
                    "home": m["score"]["fullTime"]["home"],
                    "away": m["score"]["fullTime"]["away"]
                }
            }
        })

    return compute_team_stats(matches, team_id)


def collect_team_dataset(team_id: int, limit: int = 5):
    data = api_get(
        f"teams/{team_id}/matches",
        {
            "limit": limit
        }
    )

    if not data or "matches" not in data:
        return None

    matches = []
    matches_data = data["matches"][:limit]

    for m in matches_data:
        matches.append({
            "homeTeam": {
                "id": m["homeTeam"]["id"],
                "name": m["homeTeam"]["name"]
            },
            "awayTeam": {
                "id": m["awayTeam"]["id"],
                "name": m["awayTeam"]["name"]
            },
            "score": {
                "fullTime": {
                    "home": m["score"]["fullTime"]["home"],
                    "away": m["score"]["fullTime"]["away"]
                }
            }
        })

    return compute_team_stats(matches, team_id)

async def get_last_matches(team_id, limit=5):
    data = await async_api_get(
            f"teams/{team_id}/matches",
            {
                "limit": limit
            }
        )

    if not data or "matches" not in data:
        return []

    matches = []
    matches_data = data["matches"][:limit]

    for m in matches_data:
        matches.append({
            "homeTeam": {
                "id": m["homeTeam"]["id"],
                "name": m["homeTeam"]["name"]
            },
            "awayTeam": {
                "id": m["awayTeam"]["id"],
                "name": m["awayTeam"]["name"]
            },
            "score": {
                "fullTime": {
                    "home": m["score"]["fullTime"]["home"],
                    "away": m["score"]["fullTime"]["away"]
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
async def async_get_scheduled_matches_from_competition(
    code=None,
    date_from=None,
    date_to=None
):

    params = {
        "status": "SCHEDULED"
    }

    if date_from:
        params["dateFrom"] = date_from

    if date_to:
        params["dateTo"] = date_to

    endpoint = (
        f"competitions/{code}/matches"
        if code else "matches"
    )

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

def clear_expired_cache():
    now = time.time()

    expired = []

    for key, (_, ts) in CACHE.items():
        if now - ts > CACHE_TTL:
            expired.append(key)

    for key in expired:
        del CACHE[key]

async def async_find_match_in_competitions(
    home_name,
    away_name,
    date_from=None,
    date_to=None
):

    home_name = home_name.lower()
    away_name = away_name.lower()

    for league_id in COMPETITIONS.keys():

        data = await async_api_get(
            f"competitions/{league_id}/matches",
            {
                "dateFrom": date_from or datetime.now().strftime("%Y-%m-%d"),
                "dateTo": date_to or (
                    datetime.now() + timedelta(days=7)
                ).strftime("%Y-%m-%d")
            }
        )

        if not data or "matches" not in data:
            continue

        for m in data["matches"]:

            home = m["homeTeam"]["name"].lower()
            away = m["awayTeam"]["name"].lower()

            if (
                home_name in home
                and away_name in away
            ) or (
                away_name in away
                and home_name in home
            ):

                return (
                    m,
                    league_id,
                    COMPETITIONS[league_id]
                )

    return None, None, None