import os
import json
import requests
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ==============================
# CONFIG — thay bằng thông tin của bạn
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GIST_ID = os.getenv("GIST_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")   # 🔥 THAY ID ADMIN

# QR CONFIG
BANK_ID = "970436"          # MB Bank (Ví dụ)
ACCOUNT_NUMBER = "0711000283429"  # 🔥 THAY SỐ TK CỦA BẠN

# GIÁ TỪNG GÓI
AMOUNTS = {
    "GO": 50000,
    "PLUS": 100000,
    "TEAM": 200000,
}

GIST_URL = f"https://api.github.com/gists/{GIST_ID}"


# ==============================
# HÀM TẠO QR ĐỘNG
# ==============================
def generate_qr(package_name, username, amount):
    if not username:
        username = f"id{username}"

    addinfo = f"{package_name}-{username}"

    qr_url = (
        f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NUMBER}-compact.png"
        f"?amount={amount}&addInfo={addinfo}"
    )
    return qr_url


# ==============================
# LƯU USER
# ==============================
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
        print("Lỗi Gist:", e)


# ==============================
# LƯU ĐƠN HÀNG
# ==============================
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
        print("Lỗi lưu order:", e)


# ==============================
# MENU CHÍNH
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user_to_gist(user_id)

    keyboard = [
        [InlineKeyboardButton("🛒 Mua gói", callback_data="buy")],
        [InlineKeyboardButton("🎁 Gói miễn phí", callback_data="free")],
    ]

    text = (
        "🎉 **Chào mừng bạn đến với Bot!**\n\n"
        "Bạn có thể:\n"
        "- Mua gói (GO / PLUS / TEAM)\n"
        "- Nhận gói miễn phí\n"
        "Bot mẫu phục vụ học tập."
    )

    if update.message:
        await update.message.reply_markdown(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ==============================
# MENU MUA GÓI
# ==============================
async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("MAIN GO", callback_data="buy_go_main")],
        [InlineKeyboardButton("MAIN PLUS", callback_data="buy_plus_main")],
        [InlineKeyboardButton("MAIN TEAM", callback_data="buy_team_main")],
        [InlineKeyboardButton("⬅️ Quay lại", callback_data="back_main")],
    ]

    await update.callback_query.message.edit_text(
        "🛒 **Chọn gói MAIN bạn muốn mua:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ==============================
# HIỂN THỊ GÓI MAIN + QR
# ==============================
async def show_main_package(update: Update, context: ContextTypes.DEFAULT_TYPE, package):
    user = update.effective_user

    username = user.username or f"id{user.id}"
    amount = AMOUNTS[package]

    qr_url = generate_qr(package, username, amount)

    text = (
        f"📦 **GÓI MAIN {package}**\n\n"
        "Để kích hoạt gói, vui lòng gửi:\n"
        "1. Email tài khoản\n"
        "2. Ghi chú (nếu có)\n\n"
        f"💳 Số tiền cần thanh toán: `{amount:,}đ`\n"
        "📌 *Quét mã QR bên dưới để thanh toán.*\n\n"
        "⏳ Vui lòng đợi admin kiểm tra giao dịch."
    )

    await update.callback_query.message.reply_markdown(text)
    await update.callback_query.message.reply_photo(qr_url)

    context.user_data["awaiting_info"] = package


# ==============================
# MENU MIỄN PHÍ
# ==============================
async def free_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Miễn phí GO", callback_data="free_go")],
        [InlineKeyboardButton("Miễn phí EDU", callback_data="free_edu")],
        [InlineKeyboardButton("Miễn phí PLUS", callback_data="free_plus")],
        [InlineKeyboardButton("⬅️ Quay lại", callback_data="back_main")],
    ]

    await update.callback_query.message.edit_text(
        "🎁 **Chọn gói miễn phí:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def free_item(update: Update, name):
    await update.callback_query.message.edit_text(
        f"🎉 Bạn đã nhận **{name}**!\nĐây là dữ liệu demo.\n\n`DEMO-{name}-123456`",
        parse_mode="Markdown",
    )


# ==============================
# CALLBACK HANDLER
# ==============================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data

    if data == "buy":
        return await buy_menu(update, context)

    if data == "free":
        return await free_menu(update, context)

    if data == "back_main":
        return await start(update, context)

    # GÓI MAIN
    if data == "buy_go_main":
        return await show_main_package(update, context, "GO")

    if data == "buy_plus_main":
        return await show_main_package(update, context, "PLUS")

    if data == "buy_team_main":
        return await show_main_package(update, context, "TEAM")

    # FREE ITEMS
    if data == "free_go":
        return await free_item(update, "GO")

    if data == "free_edu":
        return await free_item(update, "EDU")

    if data == "free_plus":
        return await free_item(update, "PLUS")


# ==============================
# NHẬN EMAIL + GHI CHÚ
# ==============================
async def receive_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):

    package = context.user_data.get("awaiting_info")
    if not package:
        return

    user = update.effective_user
    info = update.message.text

    save_order_to_gist(
        user.id,
        {
            "username": user.username,
            "package": package,
            "info": info,
        }
    )

    # Gửi admin
    msg = (
        f"🔥 **ĐƠN HÀNG MỚI**\n\n"
        f"👤 User: @{user.username} (ID: {user.id})\n"
        f"📦 Gói: {package}\n"
        f"📩 Thông tin:\n{info}"
    )
    await context.bot.send_message(ADMIN_CHAT_ID, msg, parse_mode="Markdown")

    # Báo khách
    await update.message.reply_text(
        "✅ Thông tin đã được ghi nhận.\nAdmin sẽ hỗ trợ bạn sớm!"
    )

    context.user_data["awaiting_info"] = None


# ==============================
# RUN BOT
# ==============================
from aiohttp import web

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{os.getenv('CLOUD_RUN_SERVICE_URL')}{WEBHOOK_PATH}"

async def webhook_handler(request):
    body = await request.json()
    await app.update_queue.put(Update.de_json(body, app.bot))
    return web.Response()

async def main():
    global app
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_info))

    # Set webhook
    await app.bot.set_webhook(WEBHOOK_URL)

    # Start aiohttp server
    web_app = web.Application()
    web_app.router.add_post(WEBHOOK_PATH, webhook_handler)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))

    await site.start()

    print(f"Bot is running via webhook → {WEBHOOK_URL}")

import asyncio

if __name__ == "__main__":
    asyncio.run(main())

