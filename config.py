import os

API_KEY = os.getenv("API_KEY")
BASE_URL = "https://api.football-data.org/v4"

COMPETITIONS = {
    "WC": "FIFA World Cup",
    "CL": "UEFA Champions League",
    "BL1": "Bundesliga",
    "DED": "Eredivisie",
    "BSA": "Campeonato Brasileiro Série A",
    "PD": "Primera Division",
    "FL1": "Ligue 1",
    "ELC": "Championship",
    "PPL": "Primeira Liga",
    "EC": "European Championship",
    "SA": "Serie A",
    "PL": "Premier League"
}

CLUB_COMPETITIONS = ["CL", "BL1", "DED", "BSA", "PD", "FL1", "ELC", "PPL", "SA", "PL"]
INTERNATIONAL_COMPETITIONS = ["WC", "EC"]
FAST_COMPETITIONS = CLUB_COMPETITIONS + INTERNATIONAL_COMPETITIONS