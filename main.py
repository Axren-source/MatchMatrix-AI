from football_api import (
    find_national_team,
    find_club_team,
    collect_team_dataset,
)
from analyzer import format_analysis


def parse_match_text(text: str):
    separators = [" vs ", " VS ", " Vs ", " v ", " - "]

    for sep in separators:
        if sep in text:
            left, right = text.split(sep, 1)
            return left.strip(), right.strip()

    return None, None


def main():
    mode = input("Choose mode (club / national): ").strip().lower()
    user_input = input("Enter match (example: France vs Brazil): ").strip()

    home_name, away_name = parse_match_text(user_input)

    if not home_name or not away_name:
        print("Invalid format. Use something like: France vs Brazil")
        input("\nPress Enter to exit...")
        return

    if mode == "national":
        home_team = find_national_team(home_name)
        away_team = find_national_team(away_name)
    else:
        home_team = find_club_team(home_name)
        away_team = find_club_team(away_name)

    if not home_team:
        print(f"Could not find team: {home_name}")
        input("\nPress Enter to exit...")
        return

    if not away_team:
        print(f"Could not find team: {away_name}")
        input("\nPress Enter to exit...")
        return

    print("\nFound teams:")
    print(f"- {home_team['name']} | {', '.join(home_team.get('competition_names', []))}")
    print(f"- {away_team['name']} | {', '.join(away_team.get('competition_names', []))}")

    home_stats = collect_team_dataset(home_team["id"], recent_limit=10)
    away_stats = collect_team_dataset(away_team["id"], recent_limit=10)

    print("\nAnalysis:\n")
    print(format_analysis(home_team["name"], home_stats, away_team["name"], away_stats))

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()