import time
from football_api import api_get, normalize_team_object
from config import CLUB_COMPETITIONS, INTERNATIONAL_COMPETITIONS
import json
from datetime import datetime, timezone

TEAMS_DB_FILE = "teams_database.json"

def build_teams_database():
    print("🚀 Building database from football-data.org...")
    all_teams = {}
    
    # Combine all codes we want to index
    target_leagues = CLUB_COMPETITIONS + INTERNATIONAL_COMPETITIONS

    for code in target_leagues:
        print(f"📥 Fetching {code}...")
        data = api_get(f"competitions/{code}/teams")
        
        if data and "teams" in data:
            for t_raw in data["teams"]:
                team = normalize_team_object(t_raw)
                team_id = team["id"]
                
                if team_id not in all_teams:
                    team["competitions"] = [code]
                    all_teams[team_id] = team
                else:
                    if code not in all_teams[team_id]["competitions"]:
                        all_teams[team_id]["competitions"].append(code)
            
            print(f"✅ Added {len(data['teams'])} teams from {code}")
        
        # MANDATORY: football-data.org free tier is 10 requests per minute
        print("⏳ Waiting 6 seconds to respect rate limits...")
        time.sleep(6)

    teams_list = list(all_teams.values())
    with open(TEAMS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(teams_list),
            "teams": teams_list,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Database saved with {len(teams_list)} teams.")

if __name__ == "__main__":
    build_teams_database()