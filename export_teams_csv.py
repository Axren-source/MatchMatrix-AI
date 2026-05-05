#!/usr/bin/env python3
"""
Export teams database to CSV for easy viewing
"""
import json
import csv
from pathlib import Path

TEAMS_DB_FILE = "teams_database.json"
TEAMS_CSV_FILE = "teams_database.csv"

def export_to_csv():
    """Export JSON teams database to CSV"""
    if not Path(TEAMS_DB_FILE).exists():
        print(f"❌ {TEAMS_DB_FILE} not found!")
        print("Run 'python build_teams_db.py' first")
        return
    
    print(f"📖 Loading {TEAMS_DB_FILE}...")
    with open(TEAMS_DB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    teams = data.get("teams", [])
    print(f"✅ Loaded {len(teams)} teams")
    
    # Export to CSV
    print(f"\n📝 Exporting to {TEAMS_CSV_FILE}...")
    with open(TEAMS_CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Name", "Short Name", "TLA", "Country", "Founded", "Competitions"])
        
        for team in teams:
            competitions = ", ".join([c["name"] for c in team.get("competitions", [])])
            writer.writerow([
                team["id"],
                team.get("name", ""),
                team.get("shortName", ""),
                team.get("tla", ""),
                team.get("country", ""),
                team.get("founded", ""),
                competitions
            ])
    
    print(f"✅ Exported to {TEAMS_CSV_FILE}")
    print(f"\n📊 CSV Preview (first 10 teams):")
    with open(TEAMS_CSV_FILE, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i < 11:  # Header + 10 teams
                print(line.strip())
            else:
                break

if __name__ == "__main__":
    export_to_csv()
