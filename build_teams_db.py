#!/usr/bin/env python3
"""
Build a complete teams database by fetching from api-football.com
This creates a JSON file with all available teams globally
"""
import json
import requests
import os
from datetime import datetime, timezone

from config import API_KEY, BASE_URL

TEAMS_DB_FILE = "teams_database.json"


def build_api_params(params=None):
    params = dict(params or {})
    params["action"] = params.get("action", "get_leagues")
    params["APIkey"] = API_KEY
    return params


def get_leagues():
    url = BASE_URL
    params = build_api_params({"action": "get_leagues"})
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def get_teams_by_league(league_id):
    url = BASE_URL
    params = build_api_params({"action": "get_teams", "league_id": league_id})
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def build_teams_database():
    print(f"🔄 Building teams database from {BASE_URL}...")

    all_teams = {}
    leagues = get_leagues()

    if not leagues:
        raise RuntimeError("No leagues returned from API.")

    print(f"📥 Found {len(leagues)} leagues")

    for league in leagues:
        league_id = league.get("league_id")
        league_name = league.get("league_name") or league.get("name") or f"League {league_id}"
        country = league.get("country_name") or league.get("country")

        if not league_id:
            continue

        print(f"\n  📥 Fetching teams from {league_name} (ID: {league_id})...")
        try:
            teams = get_teams_by_league(league_id)
            if not teams:
                print(f"  ⚠️  No teams found for {league_name}")
                continue

            print(f"  ✅ Found {len(teams)} teams")
            for team in teams:
                team_id = team.get("team_key") or team.get("team_id")
                if not team_id:
                    continue

                if team_id not in all_teams:
                    all_teams[team_id] = {
                        "id": team_id,
                        "name": team.get("team_name") or team.get("name") or "Unknown",
                        "shortName": team.get("team_short_name") or team.get("short_code") or "",
                        "tla": team.get("team_name") or "",
                        "country": team.get("team_country") or country or "",
                        "founded": team.get("team_founded") or team.get("founded"),
                        "competitions": []
                    }

                competition_entry = {
                    "id": league_id,
                    "name": league_name,
                    "country": country,
                }
                if competition_entry not in all_teams[team_id]["competitions"]:
                    all_teams[team_id]["competitions"].append(competition_entry)

        except requests.exceptions.HTTPError as e:
            print(f"  ❌ HTTP error fetching {league_name}: {e}")
        except Exception as e:
            print(f"  ❌ Error fetching {league_name}: {e}")

    teams_list = list(all_teams.values())
    print(f"\n\n{'='*60}")
    print(f"✨ DATABASE COMPLETE")
    print(f"{'='*60}")
    print(f"Total teams collected: {len(teams_list)}")

    with open(TEAMS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(teams_list),
            "teams": teams_list,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }, f, ensure_ascii=False, indent=2)

    print(f"💾 Saved to {TEAMS_DB_FILE}")
    print(f"\n📋 Sample teams:")
    for team in teams_list[:5]:
        print(f"   - {team['name']} (ID: {team['id']})")

    return teams_list


if __name__ == "__main__":
    try:
        build_teams_database()
        print("\n✅ Teams database built successfully!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import sys
        sys.exit(1)
