# Teams Database System

This system stores all football teams from api-football.com in a local JSON database for fast searching.

## Setup Instructions

### 1. Build the Teams Database

Run this command to fetch all teams from the API and store them locally:

```bash
python build_teams_db.py
```

This will:
- Fetch teams from all competitions (Premier League, La Liga, Bundesliga, Serie A, Ligue 1, World Cup, European Championship, etc.)
- Store all team IDs, names, and metadata in `teams_database.json`
- Take a few minutes on first run

### 2. Export to CSV (Optional)

To view teams in a spreadsheet format:

```bash
python export_teams_csv.py
```

This creates `teams_database.csv` that you can open in Excel or Google Sheets.

### 3. Test the Database

Run the test script to verify everything works:

```bash
python test_teams.py
```

This will:
- Load the database
- Search for sample teams
- Test both club and national team finding

## How It Works

### Database Structure (`teams_database.json`)

```json
{
  "total": 1250,
  "teams": [
    {
      "id": 541,
      "name": "Real Madrid CF",
      "shortName": "Real Madrid",
      "tla": "RMA",
      "country": "Spain",
      "founded": 1902,
      "competitions": [
        {
          "code": 2,
          "name": "UEFA Champions League"
        },
        {
          "code": 140,
          "name": "La Liga"
        }
      ]
    },
    ...
  ],
  "last_updated": "2026-05-05T12:00:00"
}
```

### Database Functions

**Load the database:**
```python
from football_api import load_teams_database

teams = load_teams_database()  # Returns list of all teams
```

**Search teams by name:**
```python
from football_api import search_teams_database

results = search_teams_database("Real Madrid")
# Returns: [{"id": 541, "name": "Real Madrid CF", ...}]
```

**Find club team:**
```python
from football_api import find_club_team

team = find_club_team("Bayern Munich")
# Returns: {"id": 40, "name": "FC Bayern München", ...}
```

**Find national team:**
```python
from football_api import find_national_team

team = find_national_team("France")
# Returns: {"id": 25, "name": "France", ...}
```

## Telegram Bot Commands

### For Users

- `/start` - Show main menu
- `/help` - Show usage help
- Send "Team A vs Team B" to predict a match

### For Admin (Owner)

- `/debug` - Show teams database statistics
- `/rebuild` - Rebuild database from API (takes ~5 minutes)

## Updating the Database

To refresh the database with latest team data:

### From Terminal

```bash
python build_teams_db.py
```

### From Telegram Bot (Admin Only)

Send `/rebuild` to the bot (only owner can use this)

## Troubleshooting

### "Teams database not found"

Run: `python build_teams_db.py`

### Teams not being found

1. Make sure `teams_database.json` exists
2. Check if the team name is spelled correctly
3. Try without full names:
   - ❌ "Manchester United Football Club"
   - ✅ "Manchester United"
   - ✅ "Manchester"

### API Error 402

This means your API key has no credits. Teams database still works offline even if API fails.

## Performance

- **Database load time**: ~50ms (after first load, cached in memory)
- **Search time**: <10ms for 1000+ teams
- **Fallback**: If database missing, automatically tries API

## Files

- `build_teams_db.py` - Script to build database from API
- `export_teams_csv.py` - Script to export database to CSV
- `test_teams.py` - Script to test database functionality
- `teams_database.json` - Main database file (auto-generated)
- `teams_database.csv` - CSV export (auto-generated)
- `football_api.py` - Database functions and API integration
