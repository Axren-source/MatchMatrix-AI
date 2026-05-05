import asyncio
import pickle
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
    async_api_get,
    search_team_by_name,
    compute_team_stats,
    get_matches_by_date,
    get_last_matches,
)

import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

MODEL_FILE = "rf_model.pkl"

# =========================
# LOAD MODEL
# =========================
with open(MODEL_FILE, "rb") as f:
    model = pickle.load(f)

# =========================
# UI
# =========================
def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Today", callback_data="today")],
        [InlineKeyboardButton("📅 Tomorrow", callback_data="tomorrow")]
    ])

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ MatchMatrix AI\n\nSend:\nArsenal vs Bayern",
        reply_markup=menu()
    )

# =========================
# TODAY MATCHES
# =========================
async def today_matches(update, context):
    today = datetime.now().strftime("%Y-%m-%d")
    matches = await get_matches_by_date(today)

    keyboard = []
    for m in matches[:10]:
        keyboard.append([
            InlineKeyboardButton(
                f"{m['home']} vs {m['away']}",
                callback_data=f"match:{m['fixture_id']}"
            )
        ])

    await update.message.reply_text(
        "📅 Today Matches:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =========================
# TOMORROW MATCHES
# =========================
async def tomorrow_matches(update, context):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    matches = await get_matches_by_date(tomorrow)

    keyboard = []
    for m in matches[:10]:
        keyboard.append([
            InlineKeyboardButton(
                f"{m['home']} vs {m['away']}",
                callback_data=f"match:{m['fixture_id']}"
            )
        ])

    await update.message.reply_text(
        "📅 Tomorrow Matches:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# =========================
# ANALYZE MATCH BY ID
# =========================
async def process_match_by_id(message, fixture_id):

    await message.reply_text("⏳ Analyzing...")

    data = await async_api_get("fixtures", {"id": fixture_id})

    if not data or not data.get("response"):
        await message.reply_text("❌ Match not found")
        return

    match = data["response"][0]

    home = match["teams"]["home"]
    away = match["teams"]["away"]

    home_id = home["id"]
    away_id = away["id"]

    home_name = home["name"]
    away_name = away["name"]

    home_matches, away_matches = await asyncio.gather(
        get_last_matches(home_id),
        get_last_matches(away_id)
    )

    home_stats = compute_team_stats(home_matches, home_id)
    away_stats = compute_team_stats(away_matches, away_id)

    if not home_stats or not away_stats:
        await message.reply_text("❌ Not enough data")
        return

    # SIMPLE PROBABILITY
    home_win = home_stats["win_rate"] * 100
    away_win = away_stats["win_rate"] * 100
    draw = 100 - (home_win + away_win)

    # SCORE
    home_goals = round(home_stats["goals_scored_avg"])
    away_goals = round(away_stats["goals_scored_avg"])

    # =========================
    # BETTING TIPS (ONLY ONCE)
    # =========================
    tips = []

    if home_win > 55:
        tips.append(f"🔥 {home_name} strong favorite")
    elif away_win > 55:
        tips.append(f"🔥 {away_name} strong favorite")
    else:
        tips.append("⚖️ Balanced match")

    if home_goals + away_goals >= 3:
        tips.append("⚽ OVER 2.5 goals")
    else:
        tips.append("🔒 UNDER 2.5 goals")

    if abs(home_win - away_win) < 10:
        tips.append("🎯 Value bet: draw or underdog")

    # =========================
    # OUTPUT
    # =========================
    msg = (
        f"📊 {home_name} vs {away_name}\n\n"
        f"🏠 {home_win:.1f}%\n"
        f"🤝 {draw:.1f}%\n"
        f"✈️ {away_win:.1f}%\n\n"
        f"⚽ Score: {home_goals}-{away_goals}\n\n"
        f"💡 Tips:\n"
    )

    for t in tips:
        msg += f"- {t}\n"

    await message.reply_text(msg)

# =========================
# HANDLE BUTTON
# =========================
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "today":
        await today_matches(update, context)

    elif query.data == "tomorrow":
        await tomorrow_matches(update, context)

    elif query.data.startswith("match:"):
        _, fixture_id = query.data.split(":")
        await process_match_by_id(update, int(fixture_id))

# =========================
# HANDLE TEXT
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if "vs" not in text.lower():
        await update.message.reply_text("Use: Team A vs Team B")
        return

    home, away = text.split("vs")
    home = home.strip()
    away = away.strip()

    home_team = search_team_by_name(home)
    away_team = search_team_by_name(away)

    if not home_team or not away_team:
        await update.message.reply_text("❌ Team not found")
        return

    # Fake fixture (just compare teams)
    await process_match_by_id(update, home_team["id"])

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()