import os

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY environment variable is not set. Please set it before running the bot.")

BASE_URL = "https://v3.football.api-sports.io"

HEADERS = {
    "x-apisports-key": API_KEY
}

# ✅ USE REAL LEAGUE IDS
COMPETITIONS = {
    1: "FIFA World Cup",
    2: "UEFA Champions League",
    78: "Bundesliga",
    88: "Eredivisie",
    71: "Campeonato Brasileiro Série A",
    140: "La Liga",
    61: "Ligue 1",
    72: "Championship",
    94: "Primeira Liga",
    4: "European Championship",
    135: "Serie A",
    39: "Premier League"
}

# ✅ SPLIT TYPES
CLUB_COMPETITIONS = [2, 78, 88, 71, 140, 61, 72, 94, 135, 39]
INTERNATIONAL_COMPETITIONS = [1, 4]
