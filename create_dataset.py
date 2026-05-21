import pandas as pd
from football_api import (
    get_last_matches,
    compute_team_stats,
    api_get,
)
from config import CLUB_COMPETITIONS, INTERNATIONAL_COMPETITIONS, COMPETITIONS

OUTPUT_FILE = "dataset.csv"

def result_to_label(home_goals, away_goals):
    """Convert match result to label: 0=away win, 1=draw, 2=home win"""
    if home_goals > away_goals:
        return 2
    elif home_goals == away_goals:
        return 1
    return 0

def fetch_competition_matches(competition_code):
    """Fetch recent matches from a competition"""
    matches = []
    try:
        data = api_get(
            f"competitions/{competition_code}/matches",
            {
                "status": "FINISHED",
                "limit": 50
            }
        )
        
        if data and "matches" in data:
            matches = data["matches"][:50]  # Last 50 matches
            
    except Exception as e:
        print(f"❌ Error fetching {competition_code}: {e}")
    
    return matches

def create_dataset():
    """Create training dataset from available API data"""
    rows = []
    international_set = set(INTERNATIONAL_COMPETITIONS)
    
    # Use club competitions for faster dataset creation
    selected_competitions = ["PL", "PD", "BL1", "SA", "FL1"]  # Top 5 leagues
    
    for comp_code in selected_competitions:
        print(f"\n🔥 Processing {comp_code} - {COMPETITIONS.get(comp_code, comp_code)}")
        
        try:
            matches = fetch_competition_matches(comp_code)
            
            if not matches:
                print(f"❌ No matches found for {comp_code}")
                continue
            
            print(f"✅ Found {len(matches)} matches")
            added = 0
            
            for match in matches:
                try:
                    full_time = match.get("score", {}).get("fullTime", {})
                    home_goals = full_time.get("home")
                    away_goals = full_time.get("away")
                    
                    if home_goals is None or away_goals is None:
                        continue
                    
                    home_team = match.get("homeTeam", {})
                    away_team = match.get("awayTeam", {})
                    home_id = home_team.get("id")
                    away_id = away_team.get("id")
                    
                    # Get recent matches for both teams
                    home_matches = get_last_matches(home_id, limit=10)
                    away_matches = get_last_matches(away_id, limit=10)
                    
                    # Compute stats
                    home_stats = compute_team_stats(home_matches, home_id)
                    away_stats = compute_team_stats(away_matches, away_id)
                    
                    if not home_stats or not away_stats:
                        continue
                    
                    row = {
                        "competition_code": comp_code,
                        "home_team": home_team.get("name", ""),
                        "away_team": away_team.get("name", ""),
                        
                        "home_form": home_stats.get("form_points", 0),
                        "away_form": away_stats.get("form_points", 0),
                        
                        "home_goals_avg": round(home_stats.get("goals_scored_avg", 0), 4),
                        "away_goals_avg": round(away_stats.get("goals_scored_avg", 0), 4),
                        
                        "home_conceded_avg": round(home_stats.get("goals_conceded_avg", 0), 4),
                        "away_conceded_avg": round(away_stats.get("goals_conceded_avg", 0), 4),
                        
                        "home_goal_diff_avg": round(home_stats.get("goal_diff_avg", 0), 4),
                        "away_goal_diff_avg": round(away_stats.get("goal_diff_avg", 0), 4),
                        
                        "home_win_rate": round(home_stats.get("win_rate", 0), 4),
                        "away_win_rate": round(away_stats.get("win_rate", 0), 4),
                        
                        "home_clean_sheet_rate": round(home_stats.get("clean_sheet_rate", 0), 4),
                        "away_clean_sheet_rate": round(away_stats.get("clean_sheet_rate", 0), 4),
                        
                        "home_failed_to_score_rate": round(home_stats.get("failed_to_score_rate", 0), 4),
                        "away_failed_to_score_rate": round(away_stats.get("failed_to_score_rate", 0), 4),
                        
                        "is_international": 1 if comp_code in international_set else 0,
                        "result": result_to_label(home_goals, away_goals),
                    }
                    
                    rows.append(row)
                    added += 1
                    
                except Exception as e:
                    continue
            
            print(f"✅ Added {added} samples from {comp_code}")
            
        except Exception as e:
            print(f"❌ Error with {comp_code}: {e}")
            continue
    
    if not rows:
        print("❌ No data collected!")
        return
    
    # Create DataFrame
    df = pd.DataFrame(rows)
    
    # Save to CSV
    df.to_csv(OUTPUT_FILE, index=False)
    
    print(f"\n✅ Dataset created: {OUTPUT_FILE}")
    print(f"   Total samples: {len(df)}")
    print(f"   Columns: {len(df.columns)}")
    print(f"\nResult distribution:")
    print(df['result'].value_counts().sort_index())

if __name__ == "__main__":
    create_dataset()
