import pickle
import pandas as pd

from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from football_api import (
    find_national_team,
    find_club_team,
    collect_team_dataset,
    find_scheduled_fixture,
    get_scheduled_matches_from_competition,
)
from config import CLUB_COMPETITIONS, INTERNATIONAL_COMPETITIONS, COMPETITIONS

import os
BOT_TOKEN = os.getenv("BOT_TOKEN")
MODEL_FILE = "rf_model.pkl"


def parse_match(text):
    for sep in [" vs ", " VS ", " Vs ", " v ", " - "]:
        if sep in text:
            left, right = text.split(sep, 1)
            return left.strip(), right.strip()
    return None, None


def convert_utc_to_local(utc_string, offset_hours=7):
    try:
        dt = datetime.strptime(utc_string, "%Y-%m-%dT%H:%M:%SZ")
        local_dt = dt + timedelta(hours=offset_hours)
        return local_dt.strftime("%Y-%m-%d %H:%M"), local_dt.strftime("%A")
    except Exception:
        return utc_string, ""


def build_feature_vector(home_stats, away_stats, is_international):
    data = {
        "home_form": [home_stats["form_points"]],
        "away_form": [away_stats["form_points"]],
        "home_goals_avg": [home_stats["goals_scored_avg"]],
        "away_goals_avg": [away_stats["goals_scored_avg"]],
        "home_conceded_avg": [home_stats["goals_conceded_avg"]],
        "away_conceded_avg": [away_stats["goals_conceded_avg"]],
        "home_goal_diff_avg": [home_stats["goal_diff_avg"]],
        "away_goal_diff_avg": [away_stats["goal_diff_avg"]],
        "home_win_rate": [home_stats["win_rate"]],
        "away_win_rate": [away_stats["win_rate"]],
        "home_clean_sheet_rate": [home_stats["clean_sheet_rate"]],
        "away_clean_sheet_rate": [away_stats["clean_sheet_rate"]],
        "home_failed_to_score_rate": [home_stats["failed_to_score_rate"]],
        "away_failed_to_score_rate": [away_stats["failed_to_score_rate"]],
        "is_international": [is_international],
    }

    return pd.DataFrame(data)


def get_confidence(best_prob):
    if best_prob >= 55:
        return "High"
    if best_prob >= 45:
        return "Medium"
    return "Low"


def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("⚽ Club Match", callback_data="mode_club"),
            InlineKeyboardButton("🌍 International Match", callback_data="mode_international"),
        ],
        [
            InlineKeyboardButton("📌 Examples", callback_data="examples"),
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


with open(MODEL_FILE, "rb") as f:
    model = pickle.load(f)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ MatchMatrix AI\n\n"
        "Welcome! I analyze football matches using AI.\n\n"
        "📊 What I give:\n"
        "• Win probabilities\n"
        "• Match insights\n"
        "• Competition & time\n\n"
        "Type a match like:\n"
        "Real Madrid vs Bayern\n"
        "France vs Brazil",
        reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ How to use MatchMatrix AI\n\n"
        "Send a match in this format:\n"
        "Team A vs Team B\n\n"
        "Examples:\n"
        "• Real Madrid vs Bayern\n"
        "• Arsenal vs Barcelona\n"
        "• France vs Brazil",
        reply_markup=main_menu_keyboard()
    )

def get_scheduled_matches_by_date(date_from, date_to, competition_codes):
    all_matches = []

    for code in competition_codes:
        try:
            matches = get_scheduled_matches_from_competition(
                code,
                date_from=date_from,
                date_to=date_to
            )

            for m in matches:
                all_matches.append({
                    "home": m["homeTeam"]["name"],
                    "away": m["awayTeam"]["name"],
                    "utcDate": m["utcDate"],
                    "competition": COMPETITIONS.get(code, code)
                })

        except Exception as e:
            print(f"Error fetching matches for {code}: {e}")

    return all_matches

async def today_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.utcnow().strftime("%Y-%m-%d")

    matches = get_scheduled_matches_by_date(
        today,
        today,
        CLUB_COMPETITIONS + INTERNATIONAL_COMPETITIONS
    )

    if not matches:
        await update.message.reply_text("No matches found today.")
        return

    keyboard = []

    for m in matches[:12]:
        text = f"{m['home']} vs {m['away']}"
        keyboard.append([InlineKeyboardButton(text, callback_data=text)])

    await update.message.reply_text(
        "📅 Today's Matches 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def tomorrow_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

    matches = get_scheduled_matches_by_date(
        tomorrow,
        tomorrow,
        CLUB_COMPETITIONS + INTERNATIONAL_COMPETITIONS
    )

    if not matches:
        await update.message.reply_text("No matches found tomorrow.")
        return

    keyboard = []

    for m in matches[:12]:
        text = f"{m['home']} vs {m['away']}"
        keyboard.append([InlineKeyboardButton(text, callback_data=text)])

    await update.message.reply_text(
        "📅 Tomorrow Matches 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "mode_club":
        context.user_data["mode"] = "club"
        await query.message.reply_text("⚽ Mode set to Club Matches")

    elif query.data == "mode_international":
        context.user_data["mode"] = "international"
        await query.message.reply_text("🌍 Mode set to International Matches")

    elif query.data == "examples":
        await query.message.reply_text(
            "📌 Example matches:\n\n"
            "• Real Madrid vs Bayern\n"
            "• Arsenal vs Barcelona\n"
            "• France vs Brazil"
        )

    elif query.data == "help":
        await query.message.reply_text(
            "❓ Send match names like this:\n\n"
            "Team A vs Team B\n\n"
            "Example:\nReal Madrid vs Bayern"
        )
    
    elif " vs " in query.data:
        match_text = query.data
        fake_update = update
        fake_update.message = query.message
        fake_update.message.text = match_text
        await handle_message(fake_update, context)

def clamp_goals(value, min_goals=0, max_goals=4):
    return max(min_goals, min(max_goals, value))


def predict_scorelines(home_stats, away_stats, home_win_prob, draw_prob, away_win_prob):
    """
    Better score prediction using both:
    - model probabilities
    - team attacking / defensive stats

    Returns:
        main_score: str
        alt_scores: list[str]
        xg_home: float
        xg_away: float
    """

    # Build rough expected goals from recent stats
    home_attack = home_stats["goals_scored_avg"]
    away_attack = away_stats["goals_scored_avg"]
    home_defense = home_stats["goals_conceded_avg"]
    away_defense = away_stats["goals_conceded_avg"]

    # Simple xG-style estimate
    xg_home = (home_attack * 0.65) + (away_defense * 0.35)
    xg_away = (away_attack * 0.65) + (home_defense * 0.35)

    # Slight adjustment from match outcome probabilities
    prob_diff = home_win_prob - away_win_prob

    if prob_diff > 12:
        xg_home += 0.25
        xg_away -= 0.10
    elif prob_diff < -12:
        xg_home -= 0.10
        xg_away += 0.25

    # Strong draw chance = pull scores closer together
    if draw_prob >= 32:
        avg_xg = (xg_home + xg_away) / 2
        xg_home = (xg_home * 0.7) + (avg_xg * 0.3)
        xg_away = (xg_away * 0.7) + (avg_xg * 0.3)

    xg_home = round(max(0.2, xg_home), 2)
    xg_away = round(max(0.2, xg_away), 2)

    main_home = clamp_goals(round(xg_home))
    main_away = clamp_goals(round(xg_away))

    # Avoid boring impossible-looking outputs for close games
    if abs(home_win_prob - away_win_prob) <= 8 and draw_prob >= 28:
        if main_home != main_away:
            main_home = 1
            main_away = 1

    main_score = f"{main_home}-{main_away}"

    # Alternative scorelines
    options = set()

    for dh, da in [
        (0, 0),
        (1, 0), (0, 1),
        (-1, 0), (0, -1),
        (1, 1), (-1, -1),
        (1, -1), (-1, 1)
    ]:
        h = clamp_goals(main_home + dh)
        a = clamp_goals(main_away + da)
        score = f"{h}-{a}"
        if score != main_score:
            options.add(score)

    # Rank alt scores depending on outcome tendency
    options = list(options)

    def score_rank(scoreline):
        h, a = map(int, scoreline.split("-"))

        if draw_prob >= home_win_prob and draw_prob >= away_win_prob:
            return (abs(h - a), abs(h - round(xg_home)) + abs(a - round(xg_away)))

        if home_win_prob > away_win_prob:
            preferred = 0 if h > a else 1
            return (preferred, abs(h - round(xg_home)) + abs(a - round(xg_away)))

        preferred = 0 if a > h else 1
        return (preferred, abs(h - round(xg_home)) + abs(a - round(xg_away)))

    alt_scores = sorted(options, key=score_rank)[:3]

    return main_score, alt_scores, xg_home, xg_away

def detect_match_mode(home_name, away_name, selected_mode=None):
    if selected_mode == "club":
        home_team = find_club_team(home_name)
        away_team = find_club_team(away_name)
        return home_team, away_team, 0, CLUB_COMPETITIONS

    if selected_mode == "international":
        home_team = find_national_team(home_name)
        away_team = find_national_team(away_name)
        return home_team, away_team, 1, INTERNATIONAL_COMPETITIONS

    # Auto mode: try clubs first, then national teams
    home_team = find_club_team(home_name)
    away_team = find_club_team(away_name)
    if home_team and away_team:
        return home_team, away_team, 0, CLUB_COMPETITIONS

    home_team = find_national_team(home_name)
    away_team = find_national_team(away_name)
    if home_team and away_team:
        return home_team, away_team, 1, INTERNATIONAL_COMPETITIONS

    return None, None, None, None

def generate_explanation(home_stats, away_stats):
    reasons = []

    if home_stats["form_points"] > away_stats["form_points"]:
        reasons.append("better recent form")

    if home_stats["goals_scored_avg"] > away_stats["goals_scored_avg"]:
        reasons.append("stronger attack")

    if home_stats["goals_conceded_avg"] < away_stats["goals_conceded_avg"]:
        reasons.append("better defense")

    if not reasons:
        return "Teams are evenly matched."

    return ", ".join(reasons).capitalize() + "."

async def process_match_request(message_obj, context, user_input: str):
    home_name, away_name = parse_match(user_input)

    if not home_name or not away_name:
        await message_obj.reply_text(
            "Invalid format.\n\nUse something like:\nReal Madrid vs Bayern",
            reply_markup=main_menu_keyboard()
        )
        return

    mode = context.user_data.get("mode")
    home_team, away_team, is_international, competition_codes = detect_match_mode(
        home_name, away_name, mode
    )

    if not home_team or not away_team:
        await message_obj.reply_text(
            "Team not found.\n\nTry exact names like:\n"
            "• Real Madrid CF\n"
            "• FC Bayern München\n"
            "• France\n"
            "• Brazil",
            reply_markup=main_menu_keyboard()
        )
        return

    fixture, fixture_code = find_scheduled_fixture(
        home_team["name"],
        away_team["name"],
        competition_codes
    )

    home_stats = collect_team_dataset(home_team["id"], recent_limit=10)
    away_stats = collect_team_dataset(away_team["id"], recent_limit=10)

    if home_stats is None:
        await message_obj.reply_text(
            f"Not enough recent data for {home_team['name']}.",
            reply_markup=main_menu_keyboard()
        )
        return

    if away_stats is None:
        await message_obj.reply_text(
            f"Not enough recent data for {away_team['name']}.",
            reply_markup=main_menu_keyboard()
        )
        return

    X = build_feature_vector(home_stats, away_stats, is_international)
    probs = model.predict_proba(X)[0]

    away_win = probs[0] * 100
    draw = probs[1] * 100
    home_win = probs[2] * 100

    best_prob = max(home_win, draw, away_win)
    confidence = get_confidence(best_prob)
    explanation = generate_explanation(home_stats, away_stats)

    main_score, alt_scores, xg_home, xg_away = predict_scorelines(
        home_stats,
        away_stats,
        home_win,
        draw,
        away_win
    )

    if home_win > draw and home_win > away_win:
        verdict = f"{home_team['name']} win"
    elif away_win > draw and away_win > home_win:
        verdict = f"{away_team['name']} win"
    else:
        verdict = "Draw"

    lines = []

    if fixture:
        fixture_home = fixture.get("homeTeam", {}).get("name", home_team["name"])
        fixture_away = fixture.get("awayTeam", {}).get("name", away_team["name"])
        utc_date = fixture.get("utcDate", "Unknown")
        competition_name = COMPETITIONS.get(fixture_code, fixture_code)

        local_time, day_name = convert_utc_to_local(utc_date, 7)

        lines.append("📅 Match Found")
        lines.append(f"{fixture_home} vs {fixture_away}")
        lines.append(f"🏆 {competition_name}")
        lines.append(f"🗓 {local_time} ({day_name})")
        lines.append("")
    else:
        lines.append("📊 Team-vs-team analysis")
        lines.append("No scheduled fixture found.")
        lines.append("")

    lines.append("📈 Prediction")
    lines.append(f"{home_team['name']}: {home_win:.1f}%")
    lines.append(f"Draw: {draw:.1f}%")
    lines.append(f"{away_team['name']}: {away_win:.1f}%")
    lines.append("")
    lines.append("⚽ Score Prediction")
    lines.append(f"Most likely score: {main_score}")
    lines.append(f"Other likely scores: {', '.join(alt_scores)}")
    lines.append(f"xG estimate: {home_team['name']} {xg_home:.2f} - {xg_away:.2f} {away_team['name']}")
    lines.append("")
    lines.append(f"Likely winner from score: {verdict}")
    lines.append("")
    lines.append(f"🧠 Insight: {explanation}")

    confidence_emoji = {
        "High": "🟢",
        "Medium": "🟡",
        "Low": "🔴"
    }.get(confidence, "")

    lines.append(f"🔎 Confidence: {confidence_emoji} {confidence}")

    await message_obj.reply_text(
        "\n".join(lines),
        reply_markup=main_menu_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_match_request(update.message, context, update.message.text.strip())


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", today_matches))
    app.add_handler(CommandHandler("tomorrow", tomorrow_matches))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()