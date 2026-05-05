#!/usr/bin/env python3
"""
QUICK START GUIDE
Run this to set everything up
"""

import sys
import subprocess
from pathlib import Path

print("="*60)
print("🚀 FOOTBALL BOT SETUP")
print("="*60)

# Step 1: Check environment variables
print("\n1️⃣  Checking environment variables...")
import os

api_key = os.getenv("API_KEY")
bot_token = os.getenv("BOT_TOKEN")

if not api_key:
    print("   ❌ API_KEY not set")
else:
    print("   ✅ API_KEY set")

if not bot_token:
    print("   ❌ BOT_TOKEN not set")
else:
    print("   ✅ BOT_TOKEN set")

if not api_key or not bot_token:
    print("\n   Please set environment variables:")
    print("   $env:API_KEY = 'your_key'")
    print("   $env:BOT_TOKEN = 'your_token'")
    sys.exit(1)

# Step 2: Check if database exists
print("\n2️⃣  Checking teams database...")
if Path("teams_database.json").exists():
    with open("teams_database.json", "r") as f:
        import json
        data = json.load(f)
        print(f"   ✅ Database exists: {data['total']} teams")
else:
    print("   ⚠️  Database not found")
    print("\n   Building database from API...")
    result = subprocess.run([sys.executable, "build_teams_db.py"], timeout=600)
    if result.returncode == 0:
        print("   ✅ Database built successfully!")
    else:
        print("   ❌ Failed to build database")
        sys.exit(1)

# Step 3: Test the system
print("\n3️⃣  Testing teams search...")
try:
    from football_api import find_club_team, find_national_team
    
    test_team = find_club_team("Real Madrid")
    if test_team:
        print(f"   ✅ Search works: Found '{test_team.get('name')}'")
    else:
        print("   ❌ Search failed")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Step 4: Check model file
print("\n4️⃣  Checking ML model...")
if Path("rf_model.pkl").exists():
    print("   ✅ Model file exists")
else:
    print("   ⚠️  Model not found - train with train_rf.py")

print("\n" + "="*60)
print("✨ SETUP COMPLETE!")
print("="*60)
print("\nYou can now start the bot:")
print("   python main.py")
print("\nOr run tests:")
print("   python test_teams.py")
print("="*60)
