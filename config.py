import os

API_KEY = os.getenv("API_KEY")

if not API_KEY:
    raise ValueError("❌ API_KEY not set in environment")

BASE_URL = "https://api.football-data.org/v4/"

COMPETITIONS = {
    # International
    "WC": "FIFA World Cup",
    "EC": "Euro Championship",
    
    # Europe - Top Leagues
    "PL": "Premier League",
    "PD": "La Liga",
    "BL1": "Bundesliga",
    "SA": "Serie A",
    "FL1": "Ligue 1",
    
    # Europe - Other Leagues
    "PPL": "Primeira Liga",
    "DED": "Eredivisie",
    "ELC": "Championship",
    
    # Europe - Cups
    "CL": "UEFA Champions League",
    "EL": "UEFA Europa League",
    "EC": "Euro Championship",
    
    # Americas
    "BSA": "Brasileirão",
    "MLS": "Major League Soccer",
    
    # Other
    "CLI": "Copa Libertadores",
    "CAF": "African Cup of Nations"
}

CLUB_COMPETITIONS = ["PL", "PD", "BL1", "SA", "FL1", "CL", "PPL", "DED", "ELC", "BSA", "MLS", "EL"]
INTERNATIONAL_COMPETITIONS = ["WC", "EC", "CAF"]
FAST_COMPETITIONS = ["PL", "PD", "BL1", "SA", "FL1", "CL"]