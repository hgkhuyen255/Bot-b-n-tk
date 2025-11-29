import os
import json
import requests
from fastapi import FastAPI, Request
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ======================================
# CONFIG
# ======================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GIST_ID = os.getenv("GIST_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

BANK_ID = "970436"
ACCOUNT_NUMBER = "0711000283429"

AMOUNTS = {
    "GO": 50000,
    "PLUS": 100000,
    "TEAM": 200000,
}

GIST_URL = f"https://api.github.com/gists/{GIST_ID}"

# ======================================
# HELPER: TẠO QR
# ======================================
def generate_qr(package_name, username, amount):
    addinfo = f"{package_name}-{username}"
    return (
        f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NUMBER}-compact.png"
        f"?amount={amount}&addInfo={addinfo}"
    )

# ======================================
# LƯU USER
# ======================================
def save_user_to_gist(user_id):
    try:
        headers = {
            "Authorization": f"token {GIST_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }

        gist = requests.get(GIST_URL, headers=headers).json()
        current = json.loads(gist["files"]["users.json"]["content"])

        if str(user_id) not in current:
            current[str(user_id)] = {"joined": True}

            requests.patch(
                GIST_URL,
                headers=headers,
                json={"files": {"users.json": {"content": json.dumps(current, indent=4)}}},
            )
    except Exception as e:
        print("GIST error:", e)

# ======================================
# LƯU ORDER
# ======================================
def save_order_to_gist(user_id, data):
    try:
        headers = {
            "Authorization": f"token {GIST_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }
        gist = requests.get(GIST_URL, headers=headers).json()
        current = json.loads(gist["files"]["orders.json"]["content"])

        current[str(user_id)] = data

        requests.patch(
            GIST_URL,
            headers=headers,
            json={"files": {"orders.json": {"content": json.dumps(current, indent=4)}}},
        )
    except Exception as e:
        print("Order save error:", e)

# ======================================
# START
# ======================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action("typing")

    save_user_to_gist(update.effective_user.id)

    keyboard = [
        [InlineKeyboardButton("🛒 Mua gói", callback_data="buy")],
        [InlineKeyboardButton("🎁 Gói miễn phí", callback_data="free")],
    ]

    text = (
        "🎉 **Chào mừng bạn đến Bot!**\n\n"
        "- Mua gói GO / PLUS / TEAM\n"
        "- Nhận gói miễn phí\n"
    )

    await update.message.reply_markdown(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ======================================
# MENU MUA
# ======================================
async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

    keyboard = [
        [InlineKeyboardButton("MAIN GO", callback_data="buy_go_main")],
        [InlineKeyboardButton("MAIN PLUS", callback_data="buy_plus_main")],
        [InlineKeyboardButton("MAIN TEAM", callback_data="buy_team_main")],
        [InlineKeyboardButton("⬅️ Quay lại", callback_data="back_main")],
    ]
    await update.callback_query.message.edit_text(
        "🛒 **Chọn gói MAIN:**", reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_main_package(update: Update, context, package):
    await update.callback_query.answer()

    user = update.effective_user
    username = user.username or f"id{user.id}"
    amount = AMOUNTS[package]

    qr_url = generate_qr(package, username, amount)

    text = (
        f"📦 **GÓI MAIN {package}**\n"
        f"💳 Thanh toán: `{amount:,}đ`\n"
        f"📌 Quét mã QR bên dưới.\n"
        f"⏳ Chờ admin duyệt."
    )

    await update.callback_query.message.reply_markdown(text)
    await update.callback_query.message.reply_photo(qr_url)

    context.user_data["awaiting_info"] = package

# ======================================
# FREE PACKAGES
# ======================================
async def free_menu(update: Update, context):
    await update.callback_query.answer()

    kb = [
        [InlineKeyboardButton("Miễn phí GO", callback_data="free_go")],
        [InlineKeyboardButton("Miễn phí EDU", callback_data="free_edu")],
        [InlineKeyboardButton("Miễn phí PLUS", callback_data="free_plus")],
        [InlineKeyboardButton("⬅️ Quay lại", callback_data="back_main")],
    ]

    await update.callback_query.message.edit_text(
        "🎁 **Chọn gói miễn phí:**", reply_markup=InlineKeyboardMarkup(kb)
    )

async def free_item(update: Update, name):
    await update.callback_query.answer()

    await update.callback_query.message.edit_text(
        f"🎉 Bạn nhận **{name}**!\n`DEMO-{name}-123456`",
        parse_mode="Markdown",
    )

# ======================================
# CALLBACK ROUTER
# ======================================
async def callbacks(update: Update, context):
    data = update.callback_query.data

    if data == "buy": return await buy_menu(update, context)
    if data == "free": return await free_menu(update, context)
    if data == "back_main": return await start(update, context)

    if data == "buy_go_main": return await show_main_package(update, context, "GO")
    if data == "buy_plus_main": return await show_main_package(update, context, "PLUS")
    if data == "buy_team_main": return await show_main_package(update, context, "TEAM")

    if data == "free_go": return await free_item(update, "GO")
    if data == "free_edu": return await free_item(update, "EDU")
    if data == "free_plus": return await free_item(update, "PLUS")

# ======================================
# NHẬN EMAIL / GHI CHÚ
# ======================================
async def receive_user_info(update: Update, context):
    pkg = context.user_data.get("awaiting_info")
    if not pkg:
        return

    user = update.effective_user
    info = update.message.text

    save_order_to_gist(
        user.id, {"username": user.username, "package": pkg, "info": info}
    )

    msg = (
        f"🔥 **ĐƠN MỚI**\n"
        f"👤 @{user.username} (ID: {user.id})\n"
        f"📦 Gói: {pkg}\n"
        f"📩 Info: {info}"
    )

    await context.bot.send_message(ADMIN_CHAT_ID, msg, parse_mode="Markdown")
    await update.message.reply_text("✅ Đã ghi nhận!")

    context.user_data["awaiting_info"] = None

# ======================================
# FASTAPI + WEBHOOK
# ======================================
app = FastAPI()

telegram_app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(callbacks))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_info))

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{os.getenv('CLOUD_RUN_SERVICE_URL')}{WEBHOOK_PATH}"

@app.post(WEBHOOK_PATH)
async def process_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
    except Exception as e:
        print("Webhook error:", e)
    return {"ok": True}

# REMOVE AUTO SET_WEBHOOK – CAUSES 500 ON STARTUP
