import os
import json
import requests
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ==============================
#  ENV
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GIST_ID = os.getenv("GIST_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
CLOUD_RUN_URL = os.getenv("CLOUD_RUN_SERVICE_URL")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{CLOUD_RUN_URL}{WEBHOOK_PATH}"

GIST_URL = f"https://api.github.com/gists/{GIST_ID}"

headers = {
    "Authorization": f"token {GIST_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ==============================
#  GIST HELPERS
# ==============================

def load_gist_json(filename):
    try:
        gist = requests.get(GIST_URL, headers=headers).json()
        content = gist["files"][filename]["content"]
        return json.loads(content)
    except Exception as e:
        print("GIST READ ERR:", e)
        return {}

def save_gist_json(filename, data):
    try:
        requests.patch(
            GIST_URL,
            headers=headers,
            json={"files": {filename: {"content": json.dumps(data, indent=4)}}},
        )
    except Exception as e:
        print("GIST WRITE ERR:", e)


def save_user_to_gist(user_id):
    users = load_gist_json("users.json")

    if str(user_id) not in users:
        users[str(user_id)] = {"joined": True}
        save_gist_json("users.json", users)


def save_order_to_gist(user_id, data):
    orders = load_gist_json("orders.json")
    orders[str(user_id)] = data
    save_gist_json("orders.json", orders)


# ==============================
#   TELEGRAM HANDLERS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user_to_gist(user.id)

    keyboard = [
        [{"text": "📦 Mua gói", "callback_data": "buy"}],
        [{"text": "🎁 Miễn phí", "callback_data": "free"}],
    ]
    text = (
        f"👋 Chào mừng bạn đến với bot!\n\n"
        f"👉 Chọn một tùy chọn bên dưới:"
    )

    await update.message.reply_text(
        text,
        reply_markup={"inline_keyboard": keyboard},
    )


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    cq = update.callback_query
    await cq.answer()

    if data == "buy":
        await cq.edit_message_text("Bạn muốn mua gói nào?")
    elif data == "free":
        await cq.edit_message_text("Đây là mục miễn phí!")


async def receive_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        info = update.message.text

        order_data = {
            "username": user.username,
            "info": info,
        }

        save_order_to_gist(user.id, order_data)

        msg = (
            f"📥 ĐƠN MỚI\n"
            f"👤 {user.username}\n"
            f"🆔 {user.id}\n"
            f"ℹ️ {info}\n"
        )
        await context.bot.send_message(ADMIN_CHAT_ID, msg)
        await update.message.reply_text("✔ Đã ghi nhận thông tin!")

    except Exception as e:
        print("Order error:", e)


# ==============================
#        FASTAPI + WEBHOOK
# ==============================

app = FastAPI()

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(callbacks))
telegram_app.add_handler(MessageHandler(filters.TEXT, receive_user_info))


@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
    except Exception as e:
        print("Webhook error:", e)

    return {"ok": True}


@app.get("/")
def home():
    return {"status": "running", "webhook": WEBHOOK_URL}
