import os

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY environment variable is not set. Please set it before running the bot.")

BASE_URL = "https://apiv3.apifootball.com/"

HEADERS = {}

# Known competition IDs for api-football
COMPETITIONS = {
    1: "FIFA World Cup",
    2: "UEFA Champions League",
    78: "Bundesliga",
    88: "Eredivisie",
    71: "Campeonato Brasileiro Série A",
    302: "La Liga",
    61: "Ligue 1",
    72: "Championship",
    94: "Primeira Liga",
    4: "European Championship",
    135: "Serie A",
    152: "Premier League"
}

# Split types for team lookup (use league IDs compatible with api-football)
CLUB_COMPETITIONS = [2, 78, 88, 71, 302, 61, 72, 94, 135, 152]
INTERNATIONAL_COMPETITIONS = [1, 4]

# Fast mode for today's schedule lookup if specific leagues are needed
FAST_COMPETITIONS = [152, 302, 78]  # Premier League, La Liga, Bundesliga