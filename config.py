import os

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY environment variable is not set.")

# New Base URL for football-data.org
BASE_URL = "https://api.football-data.org/v4/"

# Football-data.org uses string codes for competitions
COMPETITIONS = {
    "WC": "FIFA World Cup",
    "CL": "UEFA Champions League",
    "BL1": "Bundesliga",
    "DED": "Eredivisie",
    "BSA": "Campeonato Brasileiro Série A",
    "PD": "La Liga",
    "FL1": "Ligue 1",
    "ELC": "Championship",
    "PPL": "Primeira Liga",
    "EC": "European Championship",
    "SA": "Serie A",
    "PL": "Premier League"
}

# Tier 1 Leagues available on Free/Standard plans
CLUB_COMPETITIONS = ["PL", "PD", "BL1", "SA", "FL1", "CL", "PPL", "DED"]
INTERNATIONAL_COMPETITIONS = ["WC", "EC"]
FAST_COMPETITIONS = ["PL", "PD", "BL1"]