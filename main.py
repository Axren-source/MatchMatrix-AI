import pickle
import pandas as pd
import asyncio
import json
import math
from pathlib import Path
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
    api_get,
    async_api_get,
    async_find_match_in_competitions,
    find_national_team,
    find_club_team,
    compute_team_stats,
    get_last_matches,
    find_team_by_name,
    get_standings,
    calculate_motivation,
    compute_recent_form,
    compute_h2h_advantage,
)
from analyzer import calculate_win_chances
from config import API_KEY, BASE_URL, FAST_COMPETITIONS, CLUB_COMPETITIONS, INTERNATIONAL_COMPETITIONS, COMPETITIONS

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


BASE_MODEL_FEATURES = [
    "home_form",
    "away_form",
    "home_goals_avg",
    "away_goals_avg",
    "home_conceded_avg",
    "away_conceded_avg",
    "home_goal_diff_avg",
    "away_goal_diff_avg",
    "home_win_rate",
    "away_win_rate",
    "home_clean_sheet_rate",
    "away_clean_sheet_rate",
    "home_failed_to_score_rate",
    "away_failed_to_score_rate",
    "is_international",
]

PLAYER_MODEL_FEATURES = [
    "home_player_attack",
    "away_player_attack",
    "home_player_defense",
    "away_player_defense",
]

ENGINEERED_MODEL_FEATURES = [
    "home_weighted_form",
    "away_weighted_form",
    "home_momentum",
    "away_momentum",
    "home_scoring_consistency",
    "away_scoring_consistency",
    "home_defensive_consistency",
    "away_defensive_consistency",
    "home_goal_volatility",
    "away_goal_volatility",
    "home_advantage_rating",
    "away_weakness_rating",
    "home_efficiency",
    "away_efficiency",
]


def clamp_value(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def stat(stats, key, default=0):
    if not stats:
        return default
    return stats.get(key, default)


def build_feature_vector(home_stats, away_stats, is_international, home_player_impact, away_player_impact):
    home_efficiency = stat(home_stats, "home_efficiency", stat(home_stats, "goals_scored_avg") / max(stat(home_stats, "goals_conceded_avg"), 0.35))
    away_efficiency = stat(away_stats, "away_efficiency", stat(away_stats, "goals_scored_avg") / max(stat(away_stats, "goals_conceded_avg"), 0.35))

    data = {
        "home_form": [stat(home_stats, "form_points")],
        "away_form": [stat(away_stats, "form_points")],
        "home_goals_avg": [stat(home_stats, "goals_scored_avg")],
        "away_goals_avg": [stat(away_stats, "goals_scored_avg")],
        "home_conceded_avg": [stat(home_stats, "goals_conceded_avg")],
        "away_conceded_avg": [stat(away_stats, "goals_conceded_avg")],
        "home_goal_diff_avg": [stat(home_stats, "goal_diff_avg")],
        "away_goal_diff_avg": [stat(away_stats, "goal_diff_avg")],
        "home_win_rate": [stat(home_stats, "win_rate")],
        "away_win_rate": [stat(away_stats, "win_rate")],
        "home_clean_sheet_rate": [stat(home_stats, "clean_sheet_rate")],
        "away_clean_sheet_rate": [stat(away_stats, "clean_sheet_rate")],
        "home_failed_to_score_rate": [stat(home_stats, "failed_to_score_rate")],
        "away_failed_to_score_rate": [stat(away_stats, "failed_to_score_rate")],
        "is_international": [is_international],
        "home_player_attack": [stat(home_player_impact, "attack")],
        "away_player_attack": [stat(away_player_impact, "attack")],
        "home_player_defense": [stat(home_player_impact, "defense")],
        "away_player_defense": [stat(away_player_impact, "defense")],
        "home_weighted_form": [stat(home_stats, "weighted_form", stat(home_stats, "form_points"))],
        "away_weighted_form": [stat(away_stats, "weighted_form", stat(away_stats, "form_points"))],
        "home_momentum": [stat(home_stats, "momentum")],
        "away_momentum": [stat(away_stats, "momentum")],
        "home_scoring_consistency": [stat(home_stats, "scoring_consistency")],
        "away_scoring_consistency": [stat(away_stats, "scoring_consistency")],
        "home_defensive_consistency": [stat(home_stats, "defensive_consistency")],
        "away_defensive_consistency": [stat(away_stats, "defensive_consistency")],
        "home_goal_volatility": [stat(home_stats, "goal_volatility")],
        "away_goal_volatility": [stat(away_stats, "goal_volatility")],
        "home_advantage_rating": [stat(home_stats, "home_advantage_rating")],
        "away_weakness_rating": [stat(away_stats, "away_weakness_rating")],
        "home_efficiency": [home_efficiency],
        "away_efficiency": [away_efficiency],
    }

    frame = pd.DataFrame(data)
    current_model = globals().get("model")
    expected_columns = getattr(current_model, "feature_names_in_", None)

    if expected_columns is not None:
        for column in expected_columns:
            if column not in frame.columns:
                frame[column] = 0
        return frame[list(expected_columns)]

    n_features = getattr(current_model, "n_features_in_", None)
    ordered_columns = BASE_MODEL_FEATURES + PLAYER_MODEL_FEATURES + ENGINEERED_MODEL_FEATURES

    if n_features and n_features <= len(ordered_columns):
        return frame[ordered_columns[:n_features]]

    return frame[BASE_MODEL_FEATURES]


def get_confidence(best_prob):
    if best_prob >= 55:
        return "High"
    if best_prob >= 45:
        return "Medium"
    return "Low"


def normalize_probabilities(home_win, draw, away_win, floor=3.0):
    home_win = max(home_win, floor)
    draw = max(draw, floor)
    away_win = max(away_win, floor)
    total = home_win + draw + away_win
    return (
        home_win / total * 100,
        draw / total * 100,
        away_win / total * 100,
    )


def smooth_probabilities(home_win, draw, away_win, temperature=1.06):
    # Temperature > 1 softens overconfident raw model outputs without changing the winner.
    values = [
        max(home_win / 100, 0.001) ** (1 / temperature),
        max(draw / 100, 0.001) ** (1 / temperature),
        max(away_win / 100, 0.001) ** (1 / temperature),
    ]
    total = sum(values)
    return tuple(value / total * 100 for value in values)


def extract_model_probabilities(probs):
    classes = list(getattr(model, "classes_", [0, 1, 2]))
    mapped = {}

    for label, prob in zip(classes, probs):
        try:
            mapped[int(label)] = prob * 100
        except (TypeError, ValueError):
            mapped[label] = prob * 100

    away_win = mapped.get(0, probs[0] * 100)
    draw = mapped.get(1, probs[1] * 100 if len(probs) > 1 else 0)
    home_win = mapped.get(2, probs[2] * 100 if len(probs) > 2 else 0)
    return home_win, draw, away_win


def matchup_similarity(home_stats, away_stats):
    weighted_gap = abs(stat(home_stats, "weighted_form", stat(home_stats, "form_points")) - stat(away_stats, "weighted_form", stat(away_stats, "form_points"))) / 3
    attack_gap = abs(stat(home_stats, "goals_scored_avg") - stat(away_stats, "goals_scored_avg")) / 3
    defense_gap = abs(stat(home_stats, "goals_conceded_avg") - stat(away_stats, "goals_conceded_avg")) / 3
    win_gap = abs(stat(home_stats, "win_rate") - stat(away_stats, "win_rate"))
    momentum_gap = abs(stat(home_stats, "momentum") - stat(away_stats, "momentum")) / 2
    gap = (
        weighted_gap * 0.28 +
        attack_gap * 0.22 +
        defense_gap * 0.18 +
        win_gap * 0.20 +
        momentum_gap * 0.12
    )
    return clamp_value(1 - gap, 0, 1)


def team_edge_score(home_stats, away_stats):
    return (
        (stat(home_stats, "weighted_form", stat(home_stats, "form_points")) - stat(away_stats, "weighted_form", stat(away_stats, "form_points"))) * 0.22 +
        (stat(home_stats, "goal_diff_avg") - stat(away_stats, "goal_diff_avg")) * 0.34 +
        (stat(home_stats, "momentum") - stat(away_stats, "momentum")) * 0.18 +
        stat(home_stats, "home_advantage_rating") * 0.16 +
        stat(away_stats, "away_weakness_rating") * 0.10
    )


def calibrate_probabilities(home_win, draw, away_win, home_stats, away_stats):
    home_win, draw, away_win = smooth_probabilities(home_win, draw, away_win)
    home_win, draw, away_win = normalize_probabilities(home_win, draw, away_win)

    similarity = matchup_similarity(home_stats, away_stats)
    volatility = (stat(home_stats, "goal_volatility") + stat(away_stats, "goal_volatility")) / 2
    attacking_load = stat(home_stats, "goals_scored_avg") + stat(away_stats, "goals_scored_avg")

    draw_multiplier = 0.78 + (similarity * 0.38)

    if attacking_load >= 2.8:
        draw_multiplier -= 0.18
    elif attacking_load <= 2.0 and similarity >= 0.60:
        draw_multiplier += 0.10

    draw_multiplier -= clamp_value(volatility - 1.0, 0, 1.5) * 0.10

    if similarity < 0.35:
        draw_cap = 19
    elif attacking_load >= 2.8 or volatility >= 1.45:
        draw_cap = 23
    elif similarity >= 0.72 and attacking_load <= 2.4:
        draw_cap = 31
    else:
        draw_cap = 27

    calibrated_draw = clamp_value(draw * draw_multiplier, 7, draw_cap)
    delta = draw - calibrated_draw

    if delta > 0:
        home_share = clamp_value(0.5 + team_edge_score(home_stats, away_stats) / 5, 0.35, 0.65)
        home_win += delta * home_share
        away_win += delta * (1 - home_share)
    elif delta < 0:
        needed = abs(delta)
        home_share = home_win / max(home_win + away_win, 1)
        home_win = max(6, home_win - needed * home_share)
        away_win = max(6, away_win - needed * (1 - home_share))

    top_prob = max(home_win, draw, away_win)
    if volatility > 1.25 and top_prob > 48:
        reduction = min(5.0, (volatility - 1.25) * 3.5)

        if home_win == top_prob:
            home_win -= reduction
            away_win += reduction * 0.70
            draw += reduction * 0.30
        elif away_win == top_prob:
            away_win -= reduction
            home_win += reduction * 0.70
            draw += reduction * 0.30

    return normalize_probabilities(home_win, draw, away_win)


def attach_venue_context(stats, venue_stats, side):
    if not stats or not venue_stats:
        return

    stats["venue_form"] = stat(venue_stats, "form_points")
    stats["venue_goals_scored_avg"] = stat(venue_stats, "goals_scored_avg")
    stats["venue_goals_conceded_avg"] = stat(venue_stats, "goals_conceded_avg")
    stats["venue_goal_diff_avg"] = stat(venue_stats, "goal_diff_avg")
    stats["venue_matches_count"] = stat(venue_stats, "matches_count")

    if side == "home":
        stats["home_advantage_rating"] = stat(venue_stats, "home_advantage_rating")
        stats["home_efficiency"] = stat(venue_stats, "home_efficiency")
    else:
        stats["away_weakness_rating"] = stat(venue_stats, "away_weakness_rating")
        stats["away_efficiency"] = stat(venue_stats, "away_efficiency")


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

async def get_matches_by_date(date):

    all_matches = []

    for league_id in FAST_COMPETITIONS:

        data = await async_api_get(
            f"competitions/{league_id}/matches",
            {
                "dateFrom": date,
                "dateTo": date,
            }
        )

        if not data or not data.get("matches"):
            continue

        for m in data["matches"]:

            all_matches.append({
                "home": m["homeTeam"]["name"],
                "away": m["awayTeam"]["name"],
                "league": m["competition"]["name"],
                "time": m["utcDate"]
            })

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

async def today_matches(update, context):
    if not await require_vip(update.message, update.effective_user.id):
        return

    today = datetime.now().strftime("%Y-%m-%d")
    matches = await get_matches_by_date(today)
    matches.sort(key=lambda x: x.get("time", ""))
    matches = matches[:40]

    keyboard = []

    for m in matches:

        home = m["home"]
        away = m["away"]

        text = f"{home} vs {away}"

        keyboard.append([
            InlineKeyboardButton(
                text,
                callback_data=text
            )
        ])

    if not keyboard:
        await update.message.reply_text("📭 No matches today.")
        return

    await update.message.reply_text(
        f"📅 Today's Matches ({len(keyboard)}):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def tomorrow_matches(update, context):
    if not await require_vip(update.message, update.effective_user.id):
        return

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    matches = await get_matches_by_date(tomorrow)
    matches.sort(key=lambda x: x.get("time", ""))
    matches = matches[:40]

    keyboard = []

    for m in matches:

        home = m["home"]
        away = m["away"]

        text = f"{home} vs {away}"

        keyboard.append([
            InlineKeyboardButton(
                text,
                callback_data=text
            )
        ])

    if not keyboard:
        await update.message.reply_text("📭 No matches tomorrow.")
        return  
    
    await update.message.reply_text(
        f"📅 Tomorrow's Matches ({len(keyboard)}):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def get_team_players(team_id):
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

        await process_match_request(
            query.message,
            context,
            query.data,
            update.effective_user.id
        )


async def get_team_player_form(team_id):
    try:
        matches = await get_last_matches(team_id, 5)

        stats = compute_team_stats(matches, team_id)

        if not stats:
            return {
                "attack_boost": 0,
                "defense_boost": 0
            }

        return {
            "attack_boost": min(stats["goals_scored_avg"] * 0.2, 0.6),
            "defense_boost": min(
                (1.5 - stats["goals_conceded_avg"]) * 0.2,
                0.6
            )
        }

    except Exception as e:
        print("Form error:", e)

        return {
            "attack_boost": 0,
            "defense_boost": 0
        }

def clamp_goals(value, min_goals=0, max_goals=4):
    return max(min_goals, min(max_goals, value))


def poisson_probability(expected_goals, goals):
    return math.exp(-expected_goals) * (expected_goals ** goals) / math.factorial(goals)


def predict_scorelines(home_stats, away_stats, home_win_prob, draw_prob, away_win_prob, home_form_boost, away_form_boost, home_player_impact, away_player_impact, home_motivation, away_motivation):
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

    home_attack = stat(home_stats, "venue_goals_scored_avg", stat(home_stats, "goals_scored_avg"))
    away_attack = stat(away_stats, "venue_goals_scored_avg", stat(away_stats, "goals_scored_avg"))
    home_defense = stat(home_stats, "venue_goals_conceded_avg", stat(home_stats, "goals_conceded_avg"))
    away_defense = stat(away_stats, "venue_goals_conceded_avg", stat(away_stats, "goals_conceded_avg"))

    xg_home = (home_attack * 0.58) + (away_defense * 0.32) + 0.18
    xg_away = (away_attack * 0.58) + (home_defense * 0.32)

    # Venue and momentum adjustments keep scorelines closer to how this fixture is played.
    xg_home += clamp_value(stat(home_stats, "home_advantage_rating"), -0.2, 0.55) * 0.25
    xg_home += clamp_value(stat(away_stats, "away_weakness_rating"), -0.2, 0.55) * 0.20
    xg_home += clamp_value(stat(home_stats, "momentum") - stat(away_stats, "momentum"), -1.5, 1.5) * 0.08
    xg_away += clamp_value(stat(away_stats, "momentum") - stat(home_stats, "momentum"), -1.5, 1.5) * 0.08

    xg_home += stat(home_form_boost, "attack_boost")
    xg_away += stat(away_form_boost, "attack_boost")

    xg_home -= stat(away_form_boost, "defense_boost")
    xg_away -= stat(home_form_boost, "defense_boost")

    xg_home += stat(home_player_impact, "attack") * 0.25
    xg_away += stat(away_player_impact, "attack") * 0.25

    xg_home -= stat(away_player_impact, "defense") * 0.18
    xg_away -= stat(home_player_impact, "defense") * 0.18

    xg_home += stat(home_motivation, "attack_boost")
    xg_away += stat(away_motivation, "attack_boost")

    xg_home -= stat(away_motivation, "defense_boost")
    xg_away -= stat(home_motivation, "defense_boost")

    prob_edge = (home_win_prob - away_win_prob) / 100
    xg_home += clamp_value(prob_edge, -0.35, 0.35) * 0.45
    xg_away -= clamp_value(prob_edge, -0.35, 0.35) * 0.35

    if draw_prob >= 28:
        avg_xg = (xg_home + xg_away) / 2
        pull = clamp_value((draw_prob - 24) / 30, 0.12, 0.35)
        xg_home = (xg_home * (1 - pull)) + (avg_xg * pull)
        xg_away = (xg_away * (1 - pull)) + (avg_xg * pull)

    xg_home = round(clamp_value(xg_home, 0.20, 4.20), 2)
    xg_away = round(clamp_value(xg_away, 0.20, 4.20), 2)

    max_goals = 5
    matrix = {}
    outcome_totals = {"home": 0, "draw": 0, "away": 0}

    for home_goals in range(max_goals + 1):
        for away_goals in range(max_goals + 1):
            probability = poisson_probability(xg_home, home_goals) * poisson_probability(xg_away, away_goals)

            if home_goals > away_goals:
                outcome = "home"
            elif home_goals == away_goals:
                outcome = "draw"
            else:
                outcome = "away"

            matrix[(home_goals, away_goals)] = [probability, outcome]
            outcome_totals[outcome] += probability

    target_outcomes = {
        "home": home_win_prob / 100,
        "draw": draw_prob / 100,
        "away": away_win_prob / 100,
    }
    outcome_factors = {}

    for outcome, target in target_outcomes.items():
        raw = max(outcome_totals[outcome], 0.01)
        outcome_factors[outcome] = clamp_value(target / raw, 0.60, 1.65)

    adjusted_scores = []
    adjusted_total = 0

    for (home_goals, away_goals), (probability, outcome) in matrix.items():
        adjusted_probability = probability * outcome_factors[outcome]
        adjusted_total += adjusted_probability
        adjusted_scores.append((adjusted_probability, home_goals, away_goals, outcome))

    adjusted_scores = [
        (probability / adjusted_total, home_goals, away_goals, outcome)
        for probability, home_goals, away_goals, outcome in adjusted_scores
    ]
    adjusted_scores.sort(reverse=True)

    preferred_outcome = max(target_outcomes, key=target_outcomes.get)
    main_probability, main_home, main_away, main_outcome = adjusted_scores[0]

    if preferred_outcome != main_outcome and target_outcomes[preferred_outcome] - target_outcomes[main_outcome] > 0.08:
        for probability, home_goals, away_goals, outcome in adjusted_scores:
            if outcome == preferred_outcome:
                main_probability, main_home, main_away, main_outcome = probability, home_goals, away_goals, outcome
                break

    main_score = f"{main_home}-{main_away}"
    alt_scores = []

    for probability, home_goals, away_goals, outcome in adjusted_scores:
        score = f"{home_goals}-{away_goals}"
        if score == main_score or score in alt_scores:
            continue
        alt_scores.append(score)
        if len(alt_scores) == 3:
            break

    return main_score, alt_scores, xg_home, xg_away

def generate_betting_tips(home_name, away_name, home_stats, away_stats, home_win, draw, away_win, xg_home, xg_away):
    tips = []
    total_xg = xg_home + xg_away
    best_prob = max(home_win, draw, away_win)
    similarity = matchup_similarity(home_stats, away_stats)
    volatility = (stat(home_stats, "goal_volatility") + stat(away_stats, "goal_volatility")) / 2
    risky = best_prob < 46 or abs(home_win - away_win) < 8 or volatility > 1.55

    if home_win >= 56 and not risky:
        tips.append(f"High-confidence lean: {home_name} win")
    elif away_win >= 56 and not risky:
        tips.append(f"High-confidence lean: {away_name} win")
    elif home_win >= 48 and home_win > away_win:
        tips.append(f"Safer angle: {home_name} double chance")
    elif away_win >= 48 and away_win > home_win:
        tips.append(f"Safer angle: {away_name} double chance")
    elif draw >= 28 and similarity >= 0.65 and total_xg <= 2.6:
        tips.append("Draw angle is live, but only as a cautious value play")

    if total_xg >= 3.0 and min(xg_home, xg_away) >= 0.95:
        tips.append("Goals market: Over 2.5 has support")
    elif total_xg <= 2.25 and volatility <= 1.25:
        tips.append("Goals market: Under 2.5 is safer")
    elif total_xg >= 2.45:
        tips.append("Goals market: Over 1.5 is the safer goals line")

    home_btts_block = stat(home_stats, "failed_to_score_rate") > 0.45 or stat(away_stats, "clean_sheet_rate") > 0.45
    away_btts_block = stat(away_stats, "failed_to_score_rate") > 0.45 or stat(home_stats, "clean_sheet_rate") > 0.45

    if xg_home >= 1.15 and xg_away >= 1.15 and not home_btts_block and not away_btts_block:
        tips.append("BTTS: Yes has a good profile")
    elif min(xg_home, xg_away) <= 0.85 or home_btts_block or away_btts_block:
        tips.append("BTTS: No is preferred")

    edge = team_edge_score(home_stats, away_stats)

    if home_win < away_win and 30 <= home_win <= 42 and edge > 0.25:
        tips.append(f"Value bet: {home_name} has upset potential")
    elif away_win < home_win and 30 <= away_win <= 42 and edge < -0.25:
        tips.append(f"Value bet: {away_name} has upset potential")

    if risky:
        tips.append("Risk flag: volatile or very close match, avoid heavy singles")

    deduped = []
    for tip in tips:
        if tip not in deduped:
            deduped.append(tip)

    return deduped[:5]


def detect_match_mode(home_name, away_name, selected_mode=None):

    home_name = home_name.strip()
    away_name = away_name.strip()

    # CLUB MODE
    if selected_mode == "club":

        home_team = find_club_team(home_name)
        away_team = find_club_team(away_name)

        if home_team and away_team:
            if home_team["id"] != away_team["id"]:
                return (
                    home_team,
                    away_team,
                    0,
                    CLUB_COMPETITIONS,
                    None,
                    None
                )

        return None, None, None, None, None, None

    # INTERNATIONAL MODE
    if selected_mode == "international":

        home_team = find_national_team(home_name)
        away_team = find_national_team(away_name)

        if home_team and away_team:
            if home_team["id"] != away_team["id"]:
                return (
                    home_team,
                    away_team,
                    1,
                    INTERNATIONAL_COMPETITIONS,
                    None,
                    None
                )

        return None, None, None, None, None, None

    # AUTO MODE
    home_team = find_team_by_name(home_name)
    away_team = find_team_by_name(away_name)

    if home_team and away_team:

        if home_team["id"] != away_team["id"]:

            is_international = 0

            national_keywords = [
                "france",
                "brazil",
                "argentina",
                "england",
                "spain",
                "germany",
                "portugal",
                "italy",
                "netherlands",
                "belgium"
            ]

            if (
                home_name.lower() in national_keywords or
                away_name.lower() in national_keywords
            ):
                is_international = 1

            return (
                home_team,
                away_team,
                is_international,
                INTERNATIONAL_COMPETITIONS if is_international else CLUB_COMPETITIONS,
                None,
                None
            )

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

    home_name = home_name.strip()
    away_name = away_name.strip()

    mode = context.user_data.get("mode")
    home_team, away_team, is_international, comps_list, comp_code, comp_name = detect_match_mode(
        home_name, away_name, mode
    )

    # If detect_match_mode failed, try searching across all competitions
    competition_info = ""

    home_motivation = {
        "attack_boost": 0,
        "defense_boost": 0,
        "text": ""
    }

    away_motivation = {
        "attack_boost": 0,
        "defense_boost": 0,
        "text": ""
    }

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
    
    await message_obj.reply_text(
        f"🔍 Found teams:\n"
        f"🏠 Home: {home_team['name']} (ID: {home_team['id']})\n"
        f"✈️ Away: {away_team['name']} (ID: {away_team['id']})\n\n"
        "⏳ Analyzing..."
    )
    
    fixture_data = await async_find_match_in_competitions(
        home_team["name"],
        away_team["name"]
    )
    if fixture_data and fixture_data[0]:
        competition_info = f"\n🏆 {fixture_data[2]}"

    standings = None
    if fixture_data and fixture_data[1] in [
        "PL",
        "PD",
        "BL1",
        "SA",
        "FL1"
    ]:

        standings = await get_standings(
        fixture_data[1]
    )

    if standings:

        home_motivation = calculate_motivation(
            standings,
            home_team["name"]
        )

        away_motivation = calculate_motivation(
            standings,
            away_team["name"]
        )

    # 🔥 GET MATCH DATA
    home_matches, away_matches = await asyncio.gather(
        get_last_matches(home_team["id"], 10),
        get_last_matches(away_team["id"], 10)
    )


    # 🔥 BUILD STATS (using proper team_id to determine home/away perspective)
    home_stats = compute_team_stats(home_matches, home_team['id'])
    away_stats = compute_team_stats(away_matches, away_team['id'])
    home_venue_stats = compute_team_stats(home_matches, home_team['id'], venue="home")
    away_venue_stats = compute_team_stats(away_matches, away_team['id'], venue="away")

    if not home_stats or not away_stats:
        await message_obj.reply_text("❌ Not enough data.")
        return

    # ⚡ ADD RECENT FORM WEIGHTING (recent matches count more)
    attach_venue_context(home_stats, home_venue_stats, "home")
    attach_venue_context(away_stats, away_venue_stats, "away")

    home_stats["recent_form"] = compute_recent_form(home_matches, home_team['id'])
    away_stats["recent_form"] = compute_recent_form(away_matches, away_team['id'])

    # ⚡ ADD HEAD-TO-HEAD ADVANTAGE
    h2h_advantage = await compute_h2h_advantage(home_team["id"], away_team["id"])
    home_stats["h2h_advantage"] = h2h_advantage
    away_stats["h2h_advantage"] = -h2h_advantage

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
        home_win, draw, away_win = extract_model_probabilities(probs)
        
        home_win, draw, away_win = normalize_probabilities(home_win, draw, away_win)
    except Exception as e:
        print(f"⚠️ Model prediction failed: {e}. Using statistical analysis instead.")
        # Fallback to pure statistical analysis
        home_win, draw, away_win = calculate_win_chances(home_stats, away_stats)
        home_win, draw, away_win = normalize_probabilities(home_win, draw, away_win)

    home_win, draw, away_win = calibrate_probabilities(
        home_win,
        draw,
        away_win,
        home_stats,
        away_stats
    )

    main_score, alt_scores, xg_home, xg_away = predict_scorelines(
        home_stats,
        away_stats,
        home_win,
        draw,
        away_win,
        home_form_boost,
        away_form_boost,
        home_player_impact,
        away_player_impact,
        home_motivation,
        away_motivation
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
    
    tips = generate_betting_tips(
        home_team["name"],
        away_team["name"],
        home_stats,
        away_stats,
        home_win,
        draw,
        away_win,
        xg_home,
        xg_away
    )

    if tips:
        msg += "💡 BETTING TIPS:\n"
        for i, tip in enumerate(tips[:5], 1):
            msg += f"{i}. {tip}\n"

    msg += "\n🧠 MOTIVATION:\n"

    if home_motivation["text"]:
        msg += f"{home_team['name']}: {home_motivation['text']}\n"

    if away_motivation["text"]:
        msg += f"{away_team['name']}: {away_motivation['text']}\n"
    
    msg += f"\n📈 CONFIDENCE: {'High' if max(home_win, draw, away_win) > 45 else 'Medium' if max(home_win, draw, away_win) > 35 else 'Low'}"

    await message_obj.reply_text(msg)
    print(f"✅ Prediction completed: {home_team['name']} vs {away_team['name']}")

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
