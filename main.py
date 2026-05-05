import pickle
import pandas as pd
import asyncio
import json
import sys

from pathlib import Path
import requests
from telegram import LabeledPrice
from telegram.ext import PreCheckoutQueryHandler
from datetime import datetime, timedelta, UTC

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
    async_api_get,
    find_national_team,
    find_club_team,
    async_get_scheduled_matches_from_competition,
    async_collect_team_dataset,
    async_get_scheduled_matches_from_competition,
)
from config import API_KEY, BASE_URL, FAST_COMPETITIONS, CLUB_COMPETITIONS, INTERNATIONAL_COMPETITIONS

import os
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set. Please set it before running the bot.")

MODEL_FILE = "rf_model.pkl"
OWNER_ID = 6225991784  # Replace with your Telegram user ID for admin access
VIP_FILE = Path("vip_users.json")
VIP_PRICE_STARS = 300

        
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


def build_feature_vector(home_stats, away_stats, is_international, home_player_impact, away_player_impact):
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
        "home_player_attack": [home_player_impact["attack"]],
        "away_player_attack": [away_player_impact["attack"]],
        "home_player_defense": [home_player_impact["defense"]],
        "away_player_defense": [away_player_impact["defense"]],
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
            InlineKeyboardButton("⭐ Monthly VIP", callback_data="vip_monthly"),
            InlineKeyboardButton("📌 Examples", callback_data="examples"),
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def load_vip_users():
    if VIP_FILE.exists():
        with open(VIP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_vip_users(data):
    with open(VIP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

VIP_USERS = load_vip_users()

def is_vip(user_id: int) -> bool:
    # 🔥 OWNER ALWAYS VIP
    if user_id == OWNER_ID:
        return True

    expiry = VIP_USERS.get(str(user_id))
    if not expiry:
        return False

    try:
        expiry_dt = datetime.fromisoformat(expiry)
        return expiry_dt > datetime.now(UTC)
    except Exception:
        return False

def grant_vip(user_id: int, days: int = 30):
    now = datetime.now(UTC)
    current = VIP_USERS.get(str(user_id))

    if current:
        try:
            current_dt = datetime.fromisoformat(current)
            if current_dt > now:
                new_expiry = current_dt + timedelta(days=days)
            else:
                new_expiry = now + timedelta(days=days)
        except Exception:
            new_expiry = now + timedelta(days=days)
    else:
        new_expiry = now + timedelta(days=days)

    VIP_USERS[str(user_id)] = new_expiry.isoformat()
    save_vip_users(VIP_USERS)

def vip_expiry_text(user_id: int) -> str:
    expiry = VIP_USERS.get(str(user_id))
    if not expiry:
        return "No active VIP."

    try:
        expiry_dt = datetime.fromisoformat(expiry)
        return expiry_dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "Unknown"

async def require_vip(message_obj, user_id: int):
    print("require_vip user_id =", user_id, "OWNER_ID =", OWNER_ID)
    # 👑 OWNER BYPASS
    if user_id == OWNER_ID:
        return True

    if is_vip(user_id):
        return True

    await message_obj.reply_text(
        "🔒 MatchMatrix AI is premium only.\n\n"
        "Tap ⭐ Monthly VIP to unlock full access for 30 days.",
        reply_markup=main_menu_keyboard()
    )
    return False

try:
    with open(MODEL_FILE, "rb") as f:
        model = pickle.load(f)
except FileNotFoundError:
    raise FileNotFoundError(f"Model file '{MODEL_FILE}' not found. Please train the model first using train_rf.py")
except Exception as e:
    raise Exception(f"Error loading model: {e}")


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

async def debug_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug command to check available teams"""
    user_id = update.effective_user.id
    
    # Only allow owner
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Admin only")
        return
    
    try:
        from football_api import load_teams_database, search_teams_database
        
        await update.message.reply_text("⏳ Loading teams database...")
        
        teams = load_teams_database()
        if not teams:
            await update.message.reply_text("❌ Teams database not found!\n\nRun: python build_teams_db.py")
            return
        
        msg = f"📊 Teams Database\n\n"
        msg += f"✅ Total teams: {len(teams)}\n\n"
        msg += f"📋 Sample teams:\n"
        
        for team in teams[:15]:
            msg += f"• {team.get('name')}\n"
        
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def rebuild_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rebuild teams database from API"""
    user_id = update.effective_user.id
    
    # Only allow owner
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Admin only")
        return
    
    try:
        from football_api import TEAMS_DB_CACHE
        
        await update.message.reply_text("⏳ Rebuilding teams database...\n\nThis may take a few minutes...")
        
        # Clear cache
        import subprocess
        result = subprocess.run(
            [sys.executable, "build_teams_db.py"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            await update.message.reply_text(
                "✅ Database rebuilt successfully!\n\n"
                "📊 You can now search for teams."
            )
        else:
            await update.message.reply_text(
                f"❌ Error building database:\n\n{result.stderr}"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def send_monthly_vip_invoice(message_obj, context):
    await context.bot.send_invoice(
        chat_id=message_obj.chat_id,
        title="MatchMatrix VIP - 30 Days",
        description="Unlock full premium access to MatchMatrix AI for 30 days.",
        payload="vip_monthly_30d",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice("30-Day VIP Access", VIP_PRICE_STARS)],
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    user_id = update.effective_user.id

    if payment.invoice_payload == "vip_monthly_30d":
        grant_vip(user_id, days=30)
        await update.message.reply_text(
            "✅ VIP activated!\n\n"
            f"Access valid until: {vip_expiry_text(user_id)}",
            reply_markup=main_menu_keyboard()
        )

async def vip_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # 👑 OWNER BADGE
    if user_id == OWNER_ID:
        await update.message.reply_text(
            "👑 OWNER STATUS\n\n"
            "Access: Unlimited\n"
            "Tier: Admin\n"
            "Expires: Never",
            reply_markup=main_menu_keyboard()
        )
        return

    # normal VIP check
    if is_vip(user_id):
        await update.message.reply_text(
            f"⭐ VIP active until: {vip_expiry_text(user_id)}",
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "🔒 No active VIP.\nTap ⭐ Monthly VIP to unlock.",
            reply_markup=main_menu_keyboard()
        )

async def get_scheduled_matches_by_date(date_from, date_to, competition_codes=None):
    all_matches = []

    matches = await async_get_scheduled_matches_from_competition(None, date_from=date_from, date_to=date_to)
    if isinstance(matches, Exception):
        print(f"Error fetching matches: {matches}")
        return all_matches

    for m in matches:
        home = m.get("match_hometeam_name") or m.get("homeTeam", {}).get("name")
        away = m.get("match_awayteam_name") or m.get("awayTeam", {}).get("name")
        utc_date = None
        if m.get("match_date") and m.get("match_time"):
            utc_date = f"{m.get('match_date')}T{m.get('match_time')}Z"
        else:
            utc_date = m.get("match_date") or m.get("utcDate")
        competition_name = m.get("league_name") or "Unknown"

        all_matches.append({
            "home": home,
            "away": away,
            "utcDate": utc_date,
            "competition": competition_name
        })

    return all_matches

def calculate_player_impact(players):
    attack_score = 0
    defense_score = 0

    for p in players:
        goals = float(p.get("player_goals") or p.get("goals") or 0)
        assists = float(p.get("player_assists") or p.get("assists") or 0)
        rating = float(p.get("player_rating") or p.get("rating") or 0)
        position = str(p.get("player_type") or p.get("position") or p.get("player_position") or "").lower()

        if "att" in position or "mid" in position:
            attack_score += goals * 0.3 + assists * 0.2 + rating * 0.1

        if "def" in position or "goal" in position:
            defense_score += rating * 0.2

    return {
        "attack": round(attack_score / 10, 2),
        "defense": round(defense_score / 10, 2)
    }

async def today_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await require_vip(update.message, user_id):
        return
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    
    matches = await get_scheduled_matches_by_date(
        today,
        today,
        FAST_COMPETITIONS
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
    user_id = update.effective_user.id
    if not await require_vip(update.message, user_id):
        return
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")

    matches = await get_scheduled_matches_by_date(
        tomorrow,
        tomorrow,
        FAST_COMPETITIONS
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

def get_team_players(team_id):
    url = BASE_URL
    params = {
        "action": "get_teams",
        "team_id": team_id,
        "APIkey": API_KEY,
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if isinstance(data, list) and data:
        return data[0].get("players", [])
    if isinstance(data, dict):
        return data.get("players", []) or data.get("response", []) or data.get("result", [])
    return []
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
    
    elif query.data == "vip_monthly":
        await send_monthly_vip_invoice(query.message, context)

    elif " vs " in query.data:
        match_text = query.data
        await process_match_request(
           query.message,
           context,
           match_text,
           update.effective_user.id
        )

async def get_team_player_form(team_id):
    try:
        matches = await async_collect_team_dataset(team_id, limit=5)
        stats = calculate_team_stats(matches)

        if not stats:
            return {"attack_boost": 0, "defense_boost": 0}

        return {
            "attack_boost": min(stats["goals_scored_avg"] * 0.2, 0.6),
            "defense_boost": min((1.5 - stats["goals_conceded_avg"]) * 0.2, 0.6)
        }

    except Exception:
        return {"attack_boost": 0, "defense_boost": 0}

def clamp_goals(value, min_goals=0, max_goals=4):
    return max(min_goals, min(max_goals, value))


def predict_scorelines(home_stats, away_stats, home_win_prob, draw_prob, away_win_prob, home_form_boost, away_form_boost, home_player_impact, away_player_impact):
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

# 🔥 PLAYER FORM IMPACT
    xg_home += home_form_boost["attack_boost"]
    xg_away += away_form_boost["attack_boost"]

    xg_home -= away_form_boost["defense_boost"]
    xg_away -= home_form_boost["defense_boost"]

    xg_home += home_player_impact["attack"] * 0.3
    xg_away += away_player_impact["attack"] * 0.3

    xg_home -= away_player_impact["defense"] * 0.2
    xg_away -= home_player_impact["defense"] * 0.2

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

def calculate_team_stats(matches):
    if not matches:
        return None

    wins = draws = losses = 0
    goals_for = goals_against = 0
    clean_sheets = failed_to_score = 0

    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        home = score.get("home", 0)
        away = score.get("away", 0)

        if home is None or away is None:
            continue

        goals_for += home
        goals_against += away

        if home > away:
            wins += 1
        elif home == away:
            draws += 1
        else:
            losses += 1

        if away == 0:
            clean_sheets += 1
        if home == 0:
            failed_to_score += 1

    total = max(len(matches), 1)

    return {
        "form_points": wins * 3 + draws,
        "goals_scored_avg": goals_for / total,
        "goals_conceded_avg": goals_against / total,
        "goal_diff_avg": (goals_for - goals_against) / total,
        "win_rate": wins / total,
        "clean_sheet_rate": clean_sheets / total,
        "failed_to_score_rate": failed_to_score / total
    }

async def process_match_request(message_obj, context, user_input: str, user_id: int):
    if not await require_vip(message_obj, user_id):
        return

    home_name, away_name = parse_match(user_input)

    if not home_name or not away_name:
        await message_obj.reply_text("Use format: Team A vs Team B")
        return

    await message_obj.reply_text("⏳ Analyzing...")

    mode = context.user_data.get("mode")
    home_team, away_team, is_international, _ = detect_match_mode(
        home_name, away_name, mode
    )

    if not home_team or not away_team:
        await message_obj.reply_text("❌ Team not found.")
        return

    # 🔥 GET MATCH DATA
    home_data, away_data = await asyncio.gather(
        async_api_get(f"teams/{home_team['id']}/matches", {"status": "FINISHED", "limit": 5}),
        async_api_get(f"teams/{away_team['id']}/matches", {"status": "FINISHED", "limit": 5}),
    )

    home_matches = home_data.get("matches", []) if home_data else []
    away_matches = away_data.get("matches", []) if away_data else []

    # 🔥 BUILD STATS
    home_stats = calculate_team_stats(home_matches)
    away_stats = calculate_team_stats(away_matches)

    if not home_stats or not away_stats:
        await message_obj.reply_text("❌ Not enough data.")
        return

    # 🔥 PLAYER IMPACT
    home_players = get_team_players(home_team["id"])
    away_players = get_team_players(away_team["id"])

    home_player_impact = calculate_player_impact(home_players)
    away_player_impact = calculate_player_impact(away_players)

    # 🔥 FORM BOOST
    home_form_boost = await get_team_player_form(home_team["id"])
    away_form_boost = await get_team_player_form(away_team["id"])

    # 🔥 AI MODEL
    X = build_feature_vector(
        home_stats,
        away_stats,
        is_international,
        home_player_impact,
        away_player_impact
    )

    probs = model.predict_proba(X)[0]

    away_win = probs[0] * 100
    draw = probs[1] * 100
    home_win = probs[2] * 100

    # 🔥 SCORE PREDICTION
    main_score, alt_scores, xg_home, xg_away = predict_scorelines(
        home_stats,
        away_stats,
        home_win,
        draw,
        away_win,
        home_form_boost,
        away_form_boost,
        home_player_impact,
        away_player_impact
    )

    # 🔥 RESULT
    if home_win > away_win and home_win > draw:
        verdict = f"{home_team['name']} win"
    elif away_win > home_win and away_win > draw:
        verdict = f"{away_team['name']} win"
    else:
        verdict = "Draw"

    # 🔥 OUTPUT
    msg = (
        f"📊 {home_team['name']} vs {away_team['name']}\n\n"
        f"🏠 {home_team['name']}: {home_win:.1f}%\n"
        f"🤝 Draw: {draw:.1f}%\n"
        f"✈️ {away_team['name']}: {away_win:.1f}%\n\n"
        f"⚽ Score: {main_score}\n"
        f"Alt: {', '.join(alt_scores)}\n\n"
        f"xG: {xg_home:.2f} - {xg_away:.2f}\n\n"
        f"🏆 Prediction: {verdict}"
    )

    await message_obj.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_match_request(
        update.message,
        context,
        update.message.text.strip(),
        update.effective_user.id
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("vip", vip_status))
    app.add_handler(CommandHandler("today", today_matches))
    app.add_handler(CommandHandler("tomorrow", tomorrow_matches))
    app.add_handler(CommandHandler("debug", debug_teams))
    app.add_handler(CommandHandler("rebuild", rebuild_database))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()