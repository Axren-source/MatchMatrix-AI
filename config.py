import os

API_KEY = os.getenv("API_KEY")

if not API_KEY:
    raise ValueError("❌ API_KEY not set in environment")

BASE_URL = "https://api.football-data.org/v4/"

COMPETITIONS = {
    "WC": "FIFA World Cup",
    "CL": "UEFA Champions League",
    "BL1": "Bundesliga",
    "DED": "Eredivisie",
    "BSA": "Brasileirão",
    "PD": "La Liga",
    "FL1": "Ligue 1",
    "ELC": "Championship",
    "PPL": "Primeira Liga",
    "EC": "Euro Championship",
    "SA": "Serie A",
    "PL": "Premier League"
}

CLUB_COMPETITIONS = ["PL", "PD", "BL1", "SA", "FL1", "CL", "PPL", "DED"]
INTERNATIONAL_COMPETITIONS = ["WC", "EC"]
FAST_COMPETITIONS = ["PL", "PD", "BL1"]