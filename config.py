import os

API_KEY = os.getenv("API_KEY")

BASE_URL = "https://v3.football.api-sports.io/"

HEADERS = {
    "x-apisports-key": API_KEY
}

# ✅ REAL API-FOOTBALL LEAGUE IDS
COMPETITIONS = {
    # 🌍 International
    1: "FIFA World Cup",
    4: "Euro Championship",

    # 🇪🇺 Top Leagues
    39: "Premier League",
    140: "La Liga",
    78: "Bundesliga",
    135: "Serie A",
    61: "Ligue 1",

    # 🏆 Europe
    2: "Champions League",
    3: "Europa League",

    # 🌎 Americas
    71: "Brasileirão",
    253: "MLS",

    # 🌍 Africa
    6: "African Cup of Nations"
}

# ⚡ Fast queries (use these for /today)
FAST_COMPETITIONS = [39, 140, 78, 135, 61, 2]

# ⚽ Club matches
CLUB_COMPETITIONS = [39, 140, 78, 135, 61, 2, 3]

# 🌍 International matches
INTERNATIONAL_COMPETITIONS = [1, 4, 6]

print(API_KEY)
