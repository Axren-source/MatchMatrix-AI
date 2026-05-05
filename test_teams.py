#!/usr/bin/env python3
"""
Test script to verify teams database and searching
"""
import sys
from football_api import (
    load_teams_database, 
    search_teams_database,
    find_club_team, 
    find_national_team, 
    clear_cache
)

print("🧪 Testing Teams Database\n")

# Test 1: Load database
print("1️⃣  Loading teams database...")
teams = load_teams_database()
if teams:
    print(f"✅ Database loaded: {len(teams)} teams")
else:
    print("❌ Failed to load database!")
    print("   Run 'python build_teams_db.py' first")
    sys.exit(1)

# Test 2: Direct database search
print("\n2️⃣  Testing direct database search...")
test_searches = [
    "Real Madrid",
    "Bayern",
    "Manchester United",
    "Paris",
    "Liverpool"
]

for search_term in test_searches:
    results = search_teams_database(search_term)
    if results:
        print(f"✅ '{search_term}' -> {results[0]['name']}")
    else:
        print(f"❌ '{search_term}' not found")

# Test 3: Club team finding
print("\n3️⃣  Testing find_club_team()...")
club_searches = [
    "Real Madrid",
    "Bayern Munich",
    "Manchester United",
    "Arsenal",
]

for team_name in club_searches:
    result = find_club_team(team_name)
    if result:
        print(f"✅ Found: {result.get('name')}")
    else:
        print(f"❌ Not found: {team_name}")

# Test 4: National team finding
print("\n4️⃣  Testing find_national_team()...")
national_searches = [
    "France",
    "Brazil",
    "Germany",
    "Argentina",
]

for team_name in national_searches:
    result = find_national_team(team_name)
    if result:
        print(f"✅ Found: {result.get('name')}")
    else:
        print(f"❌ Not found: {team_name}")

print("\n✨ Test complete!")

