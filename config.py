import os

API_KEY = os.getenv("API_KEY")

BASE_URL = "https://api.football-data.org/v4/"

HEADERS = {
    "X-Auth-Token": API_KEY
}

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
    "EC": "European Championship",
    "SA": "Serie A",
    "PL": "Premier League"
}

CLUB_COMPETITIONS = [
    "PL",
    "PD",
    "BL1",
    "SA",
    "FL1",
    "CL",
    "EL",
    "ELC",
    "PPL",
    "DED",
]

INTERNATIONAL_COMPETITIONS = [
    "WC",
    "EC"
]

FAST_COMPETITIONS = [
    "PL",
    "PD",
    "BL1",
    "SA",
    "FL1",
    "CL",
    "EL",
    "ELC",
    "PPL",
    "DED"
]