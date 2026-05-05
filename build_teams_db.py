#!/usr/bin/env python3
"""
Build a complete teams database by fetching from api-football.com
This creates a JSON file with all available teams globally
"""
import json
import requests
import os
from pathlib import Path
from config import API_KEY, BASE_URL, HEADERS, CLUB_COMPETITIONS, INTERNATIONAL_COMPETITIONS, COMPETITIONS

TEAMS_DB_FILE = "teams_database.json"

def build_teams_database():
    """Fetch all teams from all competitions and store in a single database"""
    print(f"🔄 Building teams database from {BASE_URL}...")
    
    all_teams = {}
    all_competitions = list(set(CLUB_COMPETITIONS + INTERNATIONAL_COMPETITIONS))
    
    for competition_code in all_competitions:
        competition_name = COMPETITIONS.get(competition_code, f"Competition {competition_code}")
        print(f"\n  📥 Fetching teams from {competition_name} (ID: {competition_code})...")
        
        try:
            url = f"{BASE_URL}/competitions/{competition_code}/teams"
            response = requests.get(url, headers=HEADERS, timeout=30)
            
            if response.status_code == 429:
                print(f"  ⚠️  Rate limit hit. Waiting...")
                import time
                time.sleep(10)
                response = requests.get(url, headers=HEADERS, timeout=30)
            
            if response.status_code != 200:
                print(f"  ❌ Error {response.status_code}: {response.text}")
                continue
            
            data = response.json()
            teams = data.get("response", [])
            
            if not teams:
                print(f"  ⚠️  No teams found for {competition_name}")
                continue
            
            print(f"  ✅ Found {len(teams)} teams")
            
            for team in teams:
                team_id = team.get("id")
                if not team_id:
                    continue
                
                team_name = team.get("name", "Unknown")
                
                if team_id not in all_teams:
                    all_teams[team_id] = {
                        "id": team_id,
                        "name": team_name,
                        "shortName": team.get("shortName", ""),
                        "tla": team.get("tla", ""),
                        "country": team.get("country", ""),
                        "founded": team.get("founded"),
                        "competitions": []
                    }
                
                # Add competition if not already there
                if competition_code not in all_teams[team_id]["competitions"]:
                    all_teams[team_id]["competitions"].append({
                        "code": competition_code,
                        "name": competition_name
                    })
        
        except Exception as e:
            print(f"  ❌ Error fetching {competition_name}: {e}")
    
    # Convert to list for easier searching
    teams_list = list(all_teams.values())
    
    print(f"\n\n{'='*60}")
    print(f"✨ DATABASE COMPLETE")
    print(f"{'='*60}")
    print(f"Total teams collected: {len(teams_list)}")
    
    # Save to file
    with open(TEAMS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(teams_list),
            "teams": teams_list,
            "last_updated": __import__("datetime").datetime.now().__import__("datetime").timezone.utc.isoformat()
        }, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Saved to {TEAMS_DB_FILE}")
    
    # Show sample
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
