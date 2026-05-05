import json
import os
import time
import asyncio
import requests
import aiohttp

from config import (
    API_KEY,
    BASE_URL,
    COMPETITIONS,
    CLUB_COMPETITIONS,
    INTERNATIONAL_COMPETITIONS,
)

session = requests.Session()
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)


def build_api_params(params=None):
    params = dict(params or {})
    params["APIkey"] = API_KEY
    return params


def normalize_api_response(data):
    if isinstance(data, dict):
        if "response" in data and isinstance(data["response"], (list, dict)):
            return data["response"]
        if "result" in data and isinstance(data["result"], (list, dict)):
            return data["result"]
        return data
    return data


async def async_api_get(url, params=None, retries=5):
    wait_time = 8
    params = build_api_params(params)

    async with aiohttp.ClientSession() as session:
        for attempt in range(retries):
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 429:
                        print(f"Rate limit hit. Waiting {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                        wait_time *= 2
                        continue

                    if response.status != 200:
                        text = await response.text()
                        print(f"API Error {response.status}: {text}")
                        if response.status == 402:
                            raise Exception("API Error 402: Forbidden. Check your API key or account permissions.")
                        response.raise_for_status()

                    return normalize_api_response(await response.json())
            except aiohttp.ClientError as e:
                if attempt == retries - 1:
                    raise e
                print(f"Attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(wait_time)
                wait_time *= 2

    raise Exception("Too many requests. Please wait and try again.")


def api_get(url, params=None, retries=5):
    wait_time = 8
    params = build_api_params(params)

    for attempt in range(retries):
        response = session.get(url, params=params, timeout=30)

        if response.status_code == 429:
            print(f"Rate limit hit. Waiting {wait_time} seconds...")
            time.sleep(wait_time)
            wait_time *= 2
            continue

        if response.status_code != 200:
            print(f"API Error {response.status_code}: {response.text}")
            if response.status_code == 402:
                raise Exception("API Error 402: Forbidden. Check your API key or account permissions.")
            response.raise_for_status()

        return normalize_api_response(response.json())

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


def clear_cache():
    """Clear all cached data"""
    if os.path.exists(CACHE_DIR):
        for file in os.listdir(CACHE_DIR):
            file_path = os.path.join(CACHE_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"Cleared cache: {file}")
            except Exception as e:
                print(f"Error clearing {file}: {e}")
    # Also clear in-memory caches
    TEAM_CACHE.clear()
    NATIONAL_TEAM_CACHE.clear()
    print("Cache cleared successfully")


# ==================== TEAMS DATABASE ====================
TEAMS_DB_FILE = "teams_database.json"
TEAMS_DB_CACHE = None

def load_teams_database():
    """Load the teams database from JSON file"""
    global TEAMS_DB_CACHE
    
    if TEAMS_DB_CACHE is not None:
        return TEAMS_DB_CACHE
    
    if not os.path.exists(TEAMS_DB_FILE):
        print(f"⚠️  Teams database not found: {TEAMS_DB_FILE}")
        print("   Run 'python build_teams_db.py' to create it")
        return None
    
    try:
        with open(TEAMS_DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            TEAMS_DB_CACHE = data.get("teams", [])
            print(f"✅ Loaded {len(TEAMS_DB_CACHE)} teams from database")
            return TEAMS_DB_CACHE
    except Exception as e:
        print(f"❌ Error loading teams database: {e}")
        return None


def search_teams_database(search_term: str):
    """Search the teams database by name, shortName, or tla"""
    teams = load_teams_database()
    if not teams:
        return []
    
    target = normalize_name(search_term)
    results = []
    
    for team in teams:
        possible_names = [
            team.get("name", ""),
            team.get("shortName", ""),
            team.get("tla", "")
        ]
        
        lowered = [normalize_name(name) for name in possible_names if name]
        
        # Exact match
        if target in lowered:
            results.insert(0, team)  # Add to front
        # Partial match
        elif any(target in name for name in lowered):
            results.append(team)
        # Reverse match (team name is substring of search)
        elif any(name in target for name in lowered):
            results.append(team)
    
    return results


def normalize_name(name: str) -> str:
    return " ".join(name.lower().strip().split())


def get_teams_from_competition(code: str, use_cache=True):
    cache_name = f"teams_{code}.json"

    if use_cache:
        cached = load_cache(cache_name)
        if cached is not None:
            return cached

    params = {
        "action": "get_teams",
        "league_id": code
    }

    try:
        data = api_get(BASE_URL, params=params)
        teams = data if isinstance(data, list) else []
        if not teams:
            print(f"Warning: No teams found for competition {code}. API response: {data}")
        save_cache(cache_name, teams)
        return teams
    except Exception as e:
        print(f"Error fetching teams for competition {code}: {e}")
        cached = load_cache(cache_name)
        if cached:
            return cached
        return []


def get_all_teams_from_competitions(codes, use_cache=True):
    all_teams = {}
    team_sources = {}

    for code in codes:
        try:
            teams = get_teams_from_competition(code, use_cache=use_cache)
            for team in teams:
                team_id = team.get("team_key") or team.get("team_id") or team.get("id")

                if not team_id:
                    continue

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
    
    if not teams:
        print(f"Warning: No teams data to search through for '{team_name}'")
        return None

    exact_match = None
    partial_matches = []

    for team in teams:
        possible_names = [
            team.get("name", ""),
            team.get("team_name", ""),
            team.get("shortName", ""),
            team.get("team_short_name", ""),
            team.get("tla", ""),
            team.get("team_alternate_name", ""),
        ]

        lowered = [normalize_name(name) for name in possible_names if name]

        # Exact match on any field
        if target in lowered:
            exact_match = team
            break

        # Partial match (target is substring of team name)
        if any(target in name for name in lowered):
            partial_matches.append(team)
        
        # Also check reverse - team name is substring of target (handles "Real Madrid CF" when searching "Real Madrid")
        if any(name in target for name in lowered):
            partial_matches.append(team)

    if exact_match:
        print(f"Found exact match for '{team_name}': {exact_match.get('name')}")
        return exact_match

    if partial_matches:
        print(f"Found partial match for '{team_name}': {partial_matches[0].get('name')}")
        return partial_matches[0]

    print(f"No team found for '{team_name}' in {len(teams)} teams")
    return None


TEAM_CACHE = {}

def find_club_team(team_name: str):
    """Find a club team - tries database first, then API"""
    key = normalize_name(team_name)

    if key in TEAM_CACHE:
        print(f"✅ Returning cached club team for '{team_name}'")
        return TEAM_CACHE[key]

    print(f"🔍 Searching for club team: '{team_name}'")
    
    # Try database first
    results = search_teams_database(team_name)
    if results:
        result = results[0]
        print(f"✅ Found '{team_name}' in database: {result.get('name')}")
        TEAM_CACHE[key] = result
        return result
    
    # Fallback to API
    print(f"📡 Database search failed, trying API...")
    teams = get_all_club_teams(use_cache=True)
    print(f"📥 Loaded {len(teams)} club teams from API")
    result = find_team_by_name(team_name, teams)

    if result:
        TEAM_CACHE[key] = result
    else:
        print(f"❌ Club team not found: '{team_name}'")

    return result

NATIONAL_TEAM_CACHE = {}

def find_national_team(team_name: str):
    """Find a national team - tries database first, then API"""
    key = normalize_name(team_name)

    if key in NATIONAL_TEAM_CACHE:
        print(f"✅ Returning cached national team for '{team_name}'")
        return NATIONAL_TEAM_CACHE[key]

    print(f"🔍 Searching for national team: '{team_name}'")
    
    # Try database first
    results = search_teams_database(team_name)
    if results:
        result = results[0]
        print(f"✅ Found '{team_name}' in database: {result.get('name')}")
        NATIONAL_TEAM_CACHE[key] = result
        return result
    
    # Fallback to API
    print(f"📡 Database search failed, trying API...")
    teams = get_all_national_teams(use_cache=True)
    print(f"📥 Loaded {len(teams)} national teams from API")
    result = find_team_by_name(team_name, teams)

    if result:
        NATIONAL_TEAM_CACHE[key] = result
    else:
        print(f"❌ National team not found: '{team_name}'")

    return result


async def async_get_recent_team_matches(team_id: int, limit: int = 10, use_cache=True):
    cache_name = f"matches_{team_id}_{limit}.json"

    if use_cache:
        cached = load_cache(cache_name)
        if cached is not None:
            return cached

    today = __import__("datetime").datetime.utcnow().date()
    from_date = (today - __import__("datetime").timedelta(days=120)).isoformat()
    to_date = today.isoformat()

    params = {
        "action": "get_events",
        "team_id": team_id,
        "from": from_date,
        "to": to_date
    }

    data = await async_api_get(BASE_URL, params=params)
    matches = data if isinstance(data, list) else []

    # Filter to finished matches and keep most recent first
    filtered = []
    for match in matches:
        status = str(match.get("match_status", "")).lower()
        if status in ["finished", "ft", "full time", "completed"]:
            filtered.append(match)

    def sort_key(match):
        dt = match.get("match_date")
        if match.get("match_time"):
            dt = f"{dt} {match.get('match_time')}"
        return dt or ""

    filtered.sort(key=sort_key, reverse=True)
    result = filtered[:limit]

    if use_cache:
        save_cache(cache_name, result)
    return result


async def async_collect_team_dataset(team_id: int, recent_limit: int = 20):
    matches = await async_get_recent_team_matches(team_id, limit=recent_limit)

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

    for match in matches[:recent_limit]:
        try:
            home_goals = int(match.get("match_hometeam_score") or 0)
            away_goals = int(match.get("match_awayteam_score") or 0)
        except (TypeError, ValueError):
            continue

        home_id = match.get("match_hometeam_id")
        away_id = match.get("match_awayteam_id")

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
    """
    cache_name = f"competition_matches_{code}_{season if season else 'current'}.json"

    if use_cache:
        cached = load_cache(cache_name)
        if cached is not None:
            return cached

    params = {
        "action": "get_events",
        "league_id": code,
    }

    data = api_get(BASE_URL, params=params)
    matches = data if isinstance(data, list) else []

    save_cache(cache_name, matches)
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

async def async_get_scheduled_matches_from_competition(code: str = None, date_from=None, date_to=None, use_cache=True):
    cache_key = code if code is not None else "all"
    cache_name = f"scheduled_{cache_key}_{date_from or 'none'}_{date_to or 'none'}.json"

    if use_cache:
        cached = load_cache(cache_name)
        if cached is not None:
            return cached

    params = {
        "action": "get_events"
    }
    if code is not None:
        params["league_id"] = code
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to

    data = await async_api_get(BASE_URL, params=params)
    matches = data if isinstance(data, list) else []

    filtered = []
    for match in matches:
        status = str(match.get("match_status", "")).lower()
        if status in ["not started", "ns", "scheduled", "to be played"] or not status:
            filtered.append(match)

    if use_cache:
        save_cache(cache_name, filtered)

    return filtered

def find_scheduled_match(home_name: str, away_name: str, competition_codes, date_from=None, date_to=None):
    home_name = home_name.lower().strip()
    away_name = away_name.lower().strip()

    for code in competition_codes:
        try:
            matches = get_scheduled_matches_from_competition(code, date_from=date_from, date_to=date_to)

            for match in matches:
                home = match.get("match_hometeam_name", "").lower() or match.get("homeTeam", {}).get("name", "").lower()
                away = match.get("match_awayteam_name", "").lower() or match.get("awayTeam", {}).get("name", "").lower()

                if home_name in home and away_name in away:
                    return match

                if away_name in home and home_name in away:
                    return match
        except Exception:
            continue

    return None


def team_name_matches(query: str, actual: str) -> bool:
    if not query or not actual:
        return False

    normalized_query = normalize_name(query)
    normalized_actual = normalize_name(actual)
    return normalized_query in normalized_actual or normalized_actual in normalized_query


def get_scheduled_matches_from_competition(code: str = None, date_from=None, date_to=None, use_cache=True):
    cache_key = code if code is not None else "all"
    cache_name = f"scheduled_{cache_key}_{date_from}_{date_to}.json"

    if use_cache:
        cached = load_cache(cache_name)
        if cached is not None:
            return cached

    params = {
        "action": "get_events"
    }
    if code is not None:
        params["league_id"] = code
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to

    data = api_get(BASE_URL, params=params)
    matches = data if isinstance(data, list) else []

    filtered = []
    for match in matches:
        status = str(match.get("match_status", "")).lower()
        if status in ["not started", "ns", "scheduled", "to be played"] or not status:
            filtered.append(match)

    if use_cache:
        save_cache(cache_name, filtered)

    return filtered

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
                match_home = match.get("match_hometeam_name", "") or match.get("homeTeam", {}).get("name", "")
                match_away = match.get("match_awayteam_name", "") or match.get("awayTeam", {}).get("name", "")

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