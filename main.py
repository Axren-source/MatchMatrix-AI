import pickle
import pandas as pd
import asyncio
import json

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
    HEADERS,
    find_national_team,
    find_club_team,
    get_scheduled_matches_from_competition,
    async_collect_team_dataset,
    async_get_scheduled_matches_from_competition,
)
from config import API_KEY, BASE_URL, FAST_COMPETITIONS, COMPETITIONS, CLUB_COMPETITIONS, INTERNATIONAL_COMPETITIONS

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
        from football_api import get_all_club_teams, get_all_national_teams
        
        await update.message.reply_text("⏳ Loading teams...")
        
        club_teams = get_all_club_teams(use_cache=False)
        national_teams = get_all_national_teams(use_cache=False)
        
        msg = f"📊 Team Data\n\n"
        msg += f"Club teams loaded: {len(club_teams)}\n"
        msg += f"National teams loaded: {len(national_teams)}\n\n"
        
        if club_teams:
            msg += "📋 Sample club teams:\n"
            for team in club_teams[:5]:
                msg += f"• {team.get('name')}\n"
        
        if national_teams:
            msg += "\n🌍 National teams:\n"
            for team in national_teams[:10]:
                msg += f"• {team.get('name')}\n"
        
        await update.message.reply_text(msg)
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

async def get_scheduled_matches_by_date(date_from, date_to, competition_codes):
    all_matches = []

    tasks = [async_get_scheduled_matches_from_competition(code, date_from=date_from, date_to=date_to) for code in competition_codes]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for code, matches in zip(competition_codes, results):
        if isinstance(matches, Exception):
            print(f"Error fetching matches for {code}: {matches}")
            continue
        for m in matches:
            all_matches.append({
                "home": m["homeTeam"]["name"],
                "away": m["awayTeam"]["name"],
                "utcDate": m["utcDate"],
                "competition": COMPETITIONS.get(code, code)
            })

    return all_matches

def calculate_player_impact(players):
    attack_score = 0
    defense_score = 0

    for p in players:
        stats = p.get("statistics", [{}])[0]

        goals = stats.get("goals", {}).get("total", 0) or 0
        assists = stats.get("goals", {}).get("assists", 0) or 0
        rating = stats.get("games", {}).get("rating", 0) or 0
        position = p.get("player", {}).get("position", "")

        # Attack players
        if position in ["Attacker", "Midfielder"]:
            attack_score += goals * 0.3 + assists * 0.2 + float(rating) * 0.1

        # Defense players
        if position in ["Defender", "Goalkeeper"]:
            defense_score += float(rating) * 0.2

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
    url = f"{BASE_URL}/players"
    params = {
        "team": team_id,
        "season": 2026
    }

    response = requests.get(url, headers=HEADERS, params=params)
    data = response.json()

    return data.get("response", [])
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
    """
    Estimate team strength from recent player performances
    """
    try:
        matches = await async_collect_team_dataset(team_id, recent_limit=5)
        if not matches:
            return {
                "attack_boost": 0,
                "defense_boost": 0
            }

        goals = matches["goals_scored_avg"]
        conceded = matches["goals_conceded_avg"]

        # Normalize impact
        attack_boost = min(goals * 0.2, 0.6)
        defense_boost = min((1.5 - conceded) * 0.2, 0.6)

        return {
            "attack_boost": attack_boost,
            "defense_boost": defense_boost
        }

    except Exception:
        return {
            "attack_boost": 0,
            "defense_boost": 0
        }

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

async def process_match_request(message_obj, context, user_input: str, user_id: int):
    if not await require_vip(message_obj, user_id):
        return
    home_name, away_name = parse_match(user_input)

    await message_obj.reply_text("⏳ Analyzing match...")

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
        missing = []
        if not home_team:
            missing.append(home_name)
        if not away_team:
            missing.append(away_name)
        
        await message_obj.reply_text(
            f"❌ Team not found: {', '.join(missing)}\n\n"
            "Try these exact formats:\n"
            "• Real Madrid\n"
            "• Manchester United\n"
            "• FC Bayern München\n"
            "• PSG\n"
            "• France\n"
            "• Brazil\n\n"
            "Tip: Use team's short common names.",
            reply_markup=main_menu_keyboard()
        )
        return

    try:
        home_stats, away_stats, home_form_boost, away_form_boost = await asyncio.gather(
            async_collect_team_dataset(home_team["id"], recent_limit=5),
            async_collect_team_dataset(away_team["id"], recent_limit=5),
            get_team_player_form(home_team["id"]),
            get_team_player_form(away_team["id"])
        )

        home_players = get_team_players(home_team["id"])
        away_players = get_team_players(away_team["id"])
        home_player_impact = calculate_player_impact(home_players)
        away_player_impact = calculate_player_impact(away_players)
    except Exception as e:
        error_msg = str(e)
        print(f"Error fetching data: {error_msg}")
        if "402" in error_msg:
            await message_obj.reply_text(
                "❌ API Error: Invalid API key or account issue.\n\n"
                "Please check:\n"
                "1. API_KEY environment variable is set\n"
                "2. Your API account has active credits",
                reply_markup=main_menu_keyboard()
            )
        else:
            await message_obj.reply_text(
                f"❌ Error analyzing match: {error_msg}\n\nPlease try again later.",
                reply_markup=main_menu_keyboard()
            )
        return

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

    X = build_feature_vector(home_stats, away_stats, is_international, home_player_impact, away_player_impact)
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
        away_win,
        home_form_boost,
        away_form_boost,
        home_player_impact,
        away_player_impact
    )

    if home_win > draw and home_win > away_win:
        verdict = f"{home_team['name']} win"
    elif away_win > draw and away_win > home_win:
        verdict = f"{away_team['name']} win"
    else:
        verdict = "Draw"

    lines = []

    fixture = None
    fixture_code = None
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
    
    try:
        matches = await get_scheduled_matches_by_date(today, tomorrow, FAST_COMPETITIONS)
        for m in matches:
            if home_team["name"].lower() in m["home"].lower() and away_team["name"].lower() in m["away"].lower():
                fixture = m
                fixture_code = m.get("competition")
                break
    except Exception:
        pass

    if fixture:
        fixture_home = fixture["home"]
        fixture_away = fixture["away"]
        utc_date = fixture["utcDate"]
        competition_name = fixture.get("competition", "Unknown")

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
    lines.append("🧍 Player Analysis")
    lines.append(f"{home_team['name']} attack: {home_player_impact['attack']}")
    lines.append(f"{away_team['name']} attack: {away_player_impact['attack']}")
    lines.append(f"{home_team['name']} defense: {home_player_impact['defense']}")
    lines.append(f"{away_team['name']} defense: {away_player_impact['defense']}")
    lines.append("")
    lines.append("⚽ Score Prediction")
    lines.append(f"Most likely score: {main_score}")
    lines.append(f"Other likely scores: {', '.join(alt_scores)}")
    lines.append(f"xG estimate: {home_team['name']} {xg_home:.2f} - {xg_away:.2f} {away_team['name']}")
    lines.append("")
    lines.append(f"Likely winner from score: {verdict}")
    lines.append("")
    lines.append("🧍 Player Impact")
    lines.append(f"{home_team['name']}: +{home_form_boost['attack_boost']:.2f} attack")
    lines.append(f"{away_team['name']}: +{away_form_boost['attack_boost']:.2f} attack")
    lines.append(f"{home_team['name']}: -{home_form_boost['defense_boost']:.2f} defense")
    lines.append(f"{away_team['name']}: -{away_form_boost['defense_boost']:.2f} defense")
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
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()