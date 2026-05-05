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

import hashlib

from football_api import (
    api_get,
    async_api_get,
    find_national_team,
    find_club_team,
    async_get_scheduled_matches_from_competition,
    search_team_by_name,
    async_find_match_in_competitions,
    compute_team_stats,
)
from analyzer import calculate_win_chances
from config import API_KEY, BASE_URL, FAST_COMPETITIONS, CLUB_COMPETITIONS, INTERNATIONAL_COMPETITIONS

import os
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set. Please set it before running the bot.")

MODEL_FILE = "rf_model.pkl"
OWNER_ID = 6225991784  # Replace with your Telegram user ID for admin access
VIP_FILE = Path("vip_users.json")
VIP_PRICE_STARS = 300

MATCH_BUTTON_CACHE = {}


def make_match_callback(match_text: str) -> str:
    key = f"match:{hashlib.sha1(match_text.encode('utf-8')).hexdigest()[:16]}"
    MATCH_BUTTON_CACHE[key] = match_text
    return key


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
    """Debug command - test team search from API"""
    user_id = update.effective_user.id
    
    # Only allow owner
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Admin only")
        return
    
    try:
        await update.message.reply_text("⏳ Testing API team search...")
        
        # Test search for a few known teams
        test_teams = ["Manchester United", "Barcelona", "France"]
        results = []
        
        for team_name in test_teams:
            team = find_club_team(team_name)
            if team:
                results.append(f"✅ {team['name']} (ID: {team['id']})")
            else:
                results.append(f"❌ {team_name} not found")
        
        msg = "🔍 API Team Search Test\n\n" + "\n".join(results) + "\n\n✅ API is working!"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def rebuild_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear API cache to get fresh data"""
    user_id = update.effective_user.id
    
    # Only allow owner
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Admin only")
        return
    
    try:
        from football_api import CACHE
        
        await update.message.reply_text("⏳ Clearing API cache...")
        
        # Clear cache
        CACHE.clear()
        
        await update.message.reply_text(
            "✅ API cache cleared!\n\n"
            "📊 Fresh data will be fetched on next request."
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

    competitions = competition_codes or FAST_COMPETITIONS

    for code in competitions:
        try:
            data = await async_get_scheduled_matches_from_competition(
                code,
                date_from=date_from,
                date_to=date_to
            )

            if not data:
                continue

            for m in data:
                home = m.get("homeTeam", {}).get("name")
                away = m.get("awayTeam", {}).get("name")
                utc_date = m.get("utcDate")
                competition_name = m.get("competition", {}).get("name", "Unknown")

                if home and away:
                    all_matches.append({
                        "home": home,
                        "away": away,
                        "utcDate": utc_date,
                        "competition": competition_name
                    })

        except Exception as e:
            print(f"Error fetching {code}: {e}")

    return all_matches

def calculate_player_impact(players):
    attack_score = 0
    defense_score = 0

    if not players:
        return {
            "attack": 0,
            "defense": 0
        }

    for p in players:
        try:
            # Handle different field name formats from API
            goals = float(p.get("goals") or p.get("player_goals") or 0)
            assists = float(p.get("assists") or p.get("player_assists") or 0)
            rating = float(p.get("rating") or p.get("player_rating") or 1.0)
            position = str(p.get("position") or p.get("player_position") or p.get("player_type") or "").lower()

            if position and ("att" in position or "mid" in position or "forward" in position or "winger" in position):
                attack_score += goals * 0.3 + assists * 0.2 + rating * 0.1

            if position and ("def" in position or "goal" in position or "keeper" in position or "goalkeeper" in position):
                defense_score += rating * 0.2
        except (ValueError, TypeError):
            continue

    total_players = max(len(players), 1)
    return {
        "attack": round(attack_score / max(total_players, 1), 2),
        "defense": round(defense_score / max(total_players, 1), 2)
    }

async def today_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await require_vip(update.message, user_id):
        return
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    
    await update.message.reply_text("⏳ Fetching today's matches...")
    
    matches = await get_scheduled_matches_by_date(
        today,
        today,
        FAST_COMPETITIONS
    )

    if not matches:
        # Try fetching from all competitions if fast ones fail
        print("ℹ️ No matches in fast competitions, trying all...")
        matches = await get_scheduled_matches_by_date(today, today, None)

    if not matches:
        await update.message.reply_text(
            "📭 No scheduled matches found for today.\n\n"
            "Try /tomorrow or search manually (e.g., 'Arsenal vs Liverpool')"
        )
        return

    keyboard = []
    for m in matches:
        home = m.get("homeTeam", {}).get("name")
        away = m.get("awayTeam", {}).get("name")

        home_id = m.get("homeTeam", {}).get("id")
        away_id = m.get("awayTeam", {}).get("id")

        if not home or not away or not home_id or not away_id:
            continue

        text = f"{home} vs {away}"
        callback_data = f"matchid:{home_id}:{away_id}"

        keyboard.append([
            InlineKeyboardButton(text, callback_data=callback_data)
        ])

    if not keyboard:
        await update.message.reply_text("❌ Could not parse match data.")
        return

    await update.message.reply_text(
        f"📅 Today's Matches ({len(keyboard)}):\n\n",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def tomorrow_matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await require_vip(update.message, user_id):
        return
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")

    await update.message.reply_text("⏳ Fetching tomorrow's matches...")

    matches = await get_scheduled_matches_by_date(
        tomorrow,
        tomorrow,
        FAST_COMPETITIONS
    )
    
    if not matches:
        # Try fetching from all competitions if fast ones fail
        print("ℹ️ No matches in fast competitions, trying all...")
        matches = await get_scheduled_matches_by_date(tomorrow, tomorrow, None)

    if not matches:
        await update.message.reply_text(
            "📭 No scheduled matches found for tomorrow.\n\n"
            "Try searching manually (e.g., 'Bayern vs Arsenal')"
        )
        return

    keyboard = []
    for m in matches:
        home = m.get("homeTeam", {}).get("name")
        away = m.get("awayTeam", {}).get("name")

        home_id = m.get("homeTeam", {}).get("id")
        away_id = m.get("awayTeam", {}).get("id")

        if not home or not away or not home_id or not away_id:
            continue

        text = f"{home} vs {away}"
        callback_data = f"matchid:{home_id}:{away_id}"

        keyboard.append([
            InlineKeyboardButton(text, callback_data=callback_data)
        ])

    if not keyboard:
        await update.message.reply_text("❌ Could not parse match data.")
        return

    await update.message.reply_text(
        f"📅 Tomorrow's Matches ({len(keyboard)}):\n\n",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def get_team_players(team_id):
    """Fetch team players from API"""
    try:
        params = {}
        data = api_get(f"teams/{team_id}", params)
        
        if not data:
            return []
        
        # Extract squad from team data
        squad = data.get("squad", [])
        return squad if squad else []
    except Exception as e:
        print(f"Error fetching players: {e}")
        return []
    
async def process_match_by_id(message_obj, context, home_id, away_id, user_id):
    if not await require_vip(message_obj, user_id):
        return

    await message_obj.reply_text("⏳ Analyzing match...")

    home_data, away_data = await asyncio.gather(
        async_api_get(f"teams/{home_id}"),
        async_api_get(f"teams/{away_id}")
    )

    if not home_data or not away_data:
        await message_obj.reply_text("❌ Could not fetch teams.")
        return

    home_team = home_data
    away_team = away_data


    # 🔥 SAME AS MAIN LOGIC
    home_matches, away_matches = await asyncio.gather(
        async_api_get(f"teams/{home_id}/matches", {"status": "FINISHED", "limit": 5}),
        async_api_get(f"teams/{away_id}/matches", {"status": "FINISHED", "limit": 5}),
    )

    home_stats = compute_team_stats(home_matches.get("matches", []), home_id)
    away_stats = compute_team_stats(away_matches.get("matches", []), away_id)

    # ADD THIS AFTER STATS

    home_players = get_team_players(home_id)
    away_players = get_team_players(away_id)

    home_player_impact = calculate_player_impact(home_players)
    away_player_impact = calculate_player_impact(away_players)

    home_form_boost = await get_team_player_form(home_id)
    away_form_boost = await get_team_player_form(away_id)

    X = build_feature_vector(
        home_stats,
        away_stats,
        0,
        home_player_impact,
        away_player_impact
    )

    try:
        probs = model.predict_proba(X)[0]
        away_win = probs[0] * 100
        draw = probs[1] * 100
        home_win = probs[2] * 100
    except:
        home_win, draw, away_win = calculate_win_chances(home_stats, away_stats)

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

    await message_obj.reply_text(
        f"📊 {home_team['name']} vs {away_team['name']}\n\n"
        f"🏠 {home_win:.1f}% | 🤝 {draw:.1f}% | ✈️ {away_win:.1f}%\n"
        f"⚽ Score: {main_score}"
    )

    if not home_stats or not away_stats:
        await message_obj.reply_text("❌ Not enough data.")
        return

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

    elif query.data.startswith("matchid:"):
        _, home_id, away_id = query.data.split(":")

        await process_match_by_id(
            query.message,
            context,
            int(home_id),
            int(away_id),
            update.effective_user.id
        )

async def get_team_player_form(team_id):
    try:
        data = await async_api_get(f"teams/{team_id}/matches", {"status": "FINISHED", "limit": 5})
        matches = data.get("matches", []) if data else []
        stats = compute_team_stats(matches, team_id)

        if not stats:
            return {"attack_boost": 0, "defense_boost": 0}

        return {
            "attack_boost": min(stats["goals_scored_avg"] * 0.2, 0.6),
            "defense_boost": min((1.5 - stats["goals_conceded_avg"]) * 0.2, 0.6)
        }

    except Exception as e:
        print(f"Error calculating player form: {e}")
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
    """
    Detect match type and search across ALL configured competitions.
    Returns: (home_team, away_team, is_international, competitions_list, competition_code, competition_name)
    """
    if selected_mode == "club":
        home_team = search_team_by_name(home_name)
        away_team = search_team_by_name(away_name)
        if home_team and away_team and home_team['id'] != away_team['id']:
            return home_team, away_team, 0, CLUB_COMPETITIONS, None, None
        return None, None, None, None, None, None

    if selected_mode == "international":
        home_team = search_team_by_name(home_name)
        away_team = search_team_by_name(away_name)
        if home_team and away_team and home_team['id'] != away_team['id']:
            return home_team, away_team, 1, INTERNATIONAL_COMPETITIONS, None, None
        return None, None, None, None, None, None

    # Auto mode: try clubs first, then national teams
    home_team = find_club_team(home_name)
    away_team = find_club_team(away_name)
    if home_team and away_team and home_team['id'] != away_team['id']:
        return home_team, away_team, 0, CLUB_COMPETITIONS, None, None

    home_team = find_national_team(home_name)
    away_team = find_national_team(away_name)
    if home_team and away_team and home_team['id'] != away_team['id']:
        return home_team, away_team, 1, INTERNATIONAL_COMPETITIONS, None, None

    return None, None, None, None, None, None

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

async def process_match_request(message_obj, context, user_input: str, user_id: int):
    if not await require_vip(message_obj, user_id):
        return

    home_name, away_name = parse_match(user_input)

    if not home_name or not away_name:
        await message_obj.reply_text("Use format: Team A vs Team B")
        return

    await message_obj.reply_text("⏳ Analyzing...")

    mode = context.user_data.get("mode")
    home_team, away_team, is_international, comps_list, comp_code, comp_name = detect_match_mode(
        home_name, away_name, mode
    )

    # If detect_match_mode failed, try searching across all competitions
    competition_info = ""

    # 🔥 ALWAYS fallback to API search
    if not home_team or not away_team:
        print("⚠️ Trying direct API team search...")

        home_team = find_club_team(home_name) or find_national_team(home_name)
        away_team = find_club_team(away_name) or find_national_team(away_name)

        if not home_team or not away_team:
            await message_obj.reply_text(
                "❌ Team not found.\n\nTry:\nArsenal vs Atletico Madrid"
            )
            return

    if not home_team or not away_team:
        await message_obj.reply_text("❌ Could not find match data.")
        return

    # 🔥 GET MATCH DATA
    home_data, away_data = await asyncio.gather(
        async_api_get(f"teams/{home_team['id']}/matches", {"status": "FINISHED", "limit": 5}),
        async_api_get(f"teams/{away_team['id']}/matches", {"status": "FINISHED", "limit": 5}),
    )

    home_matches = home_data.get("matches", []) if home_data else []
    away_matches = away_data.get("matches", []) if away_data else []

    # 🔥 BUILD STATS (using proper team_id to determine home/away perspective)
    home_stats = compute_team_stats(home_matches, home_team['id'])
    away_stats = compute_team_stats(away_matches, away_team['id'])

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

    # 🔥 AI MODEL - with fallback if model prediction fails
    try:
        probs = model.predict_proba(X)[0]
        away_win = probs[0] * 100
        draw = probs[1] * 100
        home_win = probs[2] * 100
    except Exception as e:
        print(f"⚠️ Model prediction failed: {e}. Using statistical analysis instead.")
        # Fallback to pure statistical analysis
        home_win, draw, away_win = calculate_win_chances(home_stats, away_stats)

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

    # 🔥 OUTPUT - Enhanced with betting tips and competition info
    msg = (
        f"📊 {home_team['name']} vs {away_team['name']}{competition_info}\n\n"
        f"💰 WIN PROBABILITIES:\n"
        f"🏠 {home_team['name']}: {home_win:.1f}%\n"
        f"🤝 Draw: {draw:.1f}%\n"
        f"✈️ {away_team['name']}: {away_win:.1f}%\n\n"
        f"⚽ PREDICTED SCORE: {main_score}\n"
        f"Alt scores: {', '.join(alt_scores)}\n"
        f"Expected Goals: {xg_home:.2f} - {xg_away:.2f}\n\n"
        f"🏆 PREDICTION: {verdict}\n\n"
    )
    
    # Add betting tips
    tips = []

    # 🏆 Match winner logic
    if home_win > 55:
        tips.append(f"🔥 {home_team['name']} likely to win")
    elif away_win > 55:
        tips.append(f"🔥 {away_team['name']} likely to win")
    elif draw > 35:
        tips.append("⚖️ Draw is a strong possibility")

    # ⚽ Goals market
    total_xg = xg_home + xg_away

    if total_xg >= 3:
        tips.append("⚽ OVER 2.5 goals looks strong")
    elif total_xg <= 2.2:
        tips.append("🔒 UNDER 2.5 goals likely")

    # 🎯 Both teams to score
    if xg_home > 1.2 and xg_away > 1.2:
        tips.append("✅ BTTS (Both Teams To Score) – YES")
    elif xg_home < 1.0 or xg_away < 1.0:
        tips.append("❌ BTTS – NO")

    # 🛡️ Clean sheet angle
    if home_stats["clean_sheet_rate"] > 0.6:
        tips.append(f"🛡️ {home_team['name']} clean sheet possible")

    # 🎲 Value bet (close match)
    if abs(home_win - away_win) < 7:
        tips.append("🎯 Value bet: Underdog or draw")

    # 📊 Confidence
    confidence = max(home_win, draw, away_win)
    
    if tips:
        msg += "💡 BETTING TIPS:\n"
        for i, tip in enumerate(tips[:5], 1):
            msg += f"{i}. {tip}\n"
    
    msg += f"\n📈 CONFIDENCE: {'High' if max(home_win, draw, away_win) > 45 else 'Medium' if max(home_win, draw, away_win) > 35 else 'Low'}"

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