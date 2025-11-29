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
# HÀM TẠO QR
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
        current_data = json.loads(gist["files"]["users.json"]["content"])

        if str(user_id) not in current_data:
            current_data[str(user_id)] = {"joined": True}

            new_file_content = {
                "files": {
                    "users.json": {
                        "content": json.dumps(current_data, indent=4)
                    }
                }
            }

            requests.patch(GIST_URL, headers=headers, json=new_file_content)

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
        current_data = json.loads(gist["files"]["orders.json"]["content"])

        current_data[str(user_id)] = data

        new_content = {
            "files": {
                "orders.json": {
                    "content": json.dumps(current_data, indent=4)
                }
            }
        }

        requests.patch(GIST_URL, headers=headers, json=new_content)

    except Exception as e:
        print("Save order error:", e)

# ======================================
# START
# ======================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user_to_gist(user_id)

    keyboard = [
        [InlineKeyboardButton("🛒 Mua gói", callback_data="buy")],
        [InlineKeyboardButton("🎁 Gói miễn phí", callback_data="free")],
    ]

    text = (
        "🎉 **Chào mừng bạn đến với Bot!**\n\n"
        "- Mua gói GO / PLUS / TEAM\n"
        "- Nhận gói miễn phí\n"
        "Bot phục vụ học tập."
    )

    await update.message.reply_markdown(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ======================================
# MENU MUA
# ======================================
async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
# GÓI FREE
# ======================================
async def free_menu(update: Update, context):
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
    await update.callback_query.message.edit_text(
        f"🎉 Bạn nhận **{name}**!\n`DEMO-{name}-123456`",
        parse_mode="Markdown",
    )

# ======================================
# CALLBACK HANDLER
# ======================================
async def callbacks(update: Update, context):
    d = update.callback_query.data

    if d == "buy": return await buy_menu(update, context)
    if d == "free": return await free_menu(update, context)
    if d == "back_main": return await start(update, context)

    if d == "buy_go_main": return await show_main_package(update, context, "GO")
    if d == "buy_plus_main": return await show_main_package(update, context, "PLUS")
    if d == "buy_team_main": return await show_main_package(update, context, "TEAM")

    if d == "free_go": return await free_item(update, "GO")
    if d == "free_edu": return await free_item(update, "EDU")
    if d == "free_plus": return await free_item(update, "PLUS")

# ======================================
# NHẬN EMAIL + GHI CHÚ
# ======================================
async def receive_user_info(update: Update, context):
    package = context.user_data.get("awaiting_info")
    if not package:
        return

    user = update.effective_user
    info = update.message.text

    save_order_to_gist(
        user.id,
        {"username": user.username, "package": package, "info": info}
    )

    msg = (
        f"🔥 **ĐƠN MỚI**\n"
        f"👤 @{user.username} (ID: {user.id})\n"
        f"📦 Gói: {package}\n"
        f"📩 Thông tin: {info}"
    )

    await context.bot.send_message(ADMIN_CHAT_ID, msg, parse_mode="Markdown")
    await update.message.reply_text("✅ Đã ghi nhận, admin sẽ hỗ trợ!")

    context.user_data["awaiting_info"] = None


# ============================================================
# FASTAPI + UVICORN SERVER —— WEBHOOK TELEGRAM
# ============================================================
app = FastAPI()

telegram_app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(callbacks))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_info))

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{os.getenv('CLOUD_RUN_SERVICE_URL')}{WEBHOOK_PATH}"

@app.post(WEBHOOK_PATH)
async def webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
    print("Webhook set:", WEBHOOK_URL)
