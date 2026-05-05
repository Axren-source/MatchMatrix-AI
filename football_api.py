import requests
import aiohttp
import asyncio
import time
from config import API_KEY, BASE_URL
import json
import os

# These two functions MUST be defined for the rest of the file to work

def api_get(endpoint, params=None):
    """Synchronous GET request for database building"""
    url = f"{BASE_URL}{endpoint.lstrip('/')}"
    headers = {"X-Auth-Token": API_KEY}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 429:
            print("⚠️ Rate limit hit. Waiting 60s...")
            time.sleep(60)
            return api_get(endpoint, params)
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None

async def async_api_get(endpoint, params=None, retries=3):
    """Asynchronous GET request for the Telegram bot"""
    url = f"{BASE_URL}{endpoint.lstrip('/')}"
    headers = {"X-Auth-Token": API_KEY}

    async with aiohttp.ClientSession(headers=headers) as session:
        for attempt in range(retries):
            try:
                async with session.get(url, params=params, timeout=20) as response:
                    if response.status == 429:
                        await asyncio.sleep(60)
                        continue
                    return await response.json() if response.status == 200 else None
            except Exception:
                await asyncio.sleep(2)
    return None

TEAMS_DB_FILE = "teams_database.json"
TEAMS_DB_CACHE = None

def normalize_name(name: str) -> str:
    """Standardize names for comparison"""
    return " ".join(name.lower().strip().split())

def get_scheduled_matches_from_competition(code: str):
    """
    Fetches all upcoming matches for a specific league (e.g., 'PL', 'PD').
    Uses the football-data.org status filter to only get 'SCHEDULED' games.
    """
    # Endpoint: /v4/competitions/{code}/matches?status=SCHEDULED
    params = {"status": "SCHEDULED"}
    data = api_get(f"competitions/{code}/matches", params=params)
    
    if data and "matches" in data:
        return data["matches"]
    return []

async def async_get_scheduled_matches_from_competition(code: str):
    """Async version for the Telegram bot's real-time updates[cite: 1, 3]"""
    params = {"status": "SCHEDULED"}
    data = await async_api_get(f"competitions/{code}/matches", params=params)
    
    if data and "matches" in data:
        return data["matches"]
    return []

def load_teams_database():
    """Load the teams database from the local JSON file[cite: 1, 2]"""
    global TEAMS_DB_CACHE
    if TEAMS_DB_CACHE is not None:
        return TEAMS_DB_CACHE
    
    if not os.path.exists(TEAMS_DB_FILE):
        print(f"⚠️ Teams database not found: {TEAMS_DB_FILE}")
        return None
    
    try:
        with open(TEAMS_DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            TEAMS_DB_CACHE = data.get("teams", [])
            return TEAMS_DB_CACHE
    except Exception as e:
        print(f"❌ Error loading teams database: {e}")
        return None

def search_teams_database(search_term: str):
    """Search for a team in the local database by name, shortName, or TLA[cite: 1]"""
    teams = load_teams_database()
    if not teams:
        return []
    
    target = normalize_name(search_term)
    results = []
    
    for team in teams:
        # Check all possible naming fields provided by football-data.org[cite: 1]
        possible_names = [
            team.get("name", ""),
            team.get("shortName", ""),
            team.get("tla", "")
        ]
        
        lowered = [normalize_name(name) for name in possible_names if name]
        
        if target in lowered:
            results.insert(0, team) # Exact match priority
        elif any(target in name for name in lowered) or any(name in target for name in lowered):
            results.append(team)
    
    return results

def normalize_team_object(team: dict):
    """
    Standardizes team data into a consistent dictionary format for football-data.org.
    """
    if not isinstance(team, dict):
        return team

    # Extract core fields using the new API schema
    team_id = team.get("id")
    name = team.get("name") or team.get("shortName") or "Unknown"
    short = team.get("shortName") or team.get("tla") or ""
    tla = team.get("tla") or ""
    
    # Safely handle the 'area' dictionary to get the country name
    area = team.get("area", {})
    if isinstance(area, dict):
        country = area.get("name", "")
    else:
        country = team.get("country", "")

    return {
        "id": team_id,
        "name": name,
        "shortName": short,
        "tla": tla,
        "country": country,
        "crest": team.get("crest") 
    }

def find_club_team(team_name: str):
    """Find a club team using the database[cite: 1]"""
    print(f"🔍 Searching for club team: '{team_name}'")
    results = search_teams_database(team_name)
    if results:
        return normalize_team_object(results[0])
    return None

def find_national_team(team_name: str):
    """Find a national team using the database[cite: 1]"""
    print(f"🌍 Searching for national team: '{team_name}'")
    results = search_teams_database(team_name)
    if results:
        return normalize_team_object(results[0])
    return None