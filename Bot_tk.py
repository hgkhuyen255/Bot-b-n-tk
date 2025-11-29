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
    ContextTypes,
)

# ==============================
# CONFIG — thay bằng token của bạn
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GIST_ID = os.getenv("GIST_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")

GIST_URL = f"https://api.github.com/gists/{GIST_ID}"

# ==============================
# Hàm lưu user vào Gist
# ==============================
def save_user_to_gist(user_id):
    try:
        headers = {
            "Authorization": f"token {GIST_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Lấy nội dung cũ
        gist = requests.get(GIST_URL, headers=headers).json()
        current_data = json.loads(gist["files"]["users.json"]["content"])

        # Nếu user chưa có → thêm vào
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
# Menu chính
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user_to_gist(user_id)

    keyboard = [
        [InlineKeyboardButton("🛒 Mua gói", callback_data="buy")],
        [InlineKeyboardButton("🎁 Gói miễn phí", callback_data="free")],
    ]

    text = (
        "🎉 **Chào mừng bạn đến với Bot Mẫu!**\n\n"
        "Bot cung cấp menu demo cho mục đích học tập và nghiên cứu.\n"
        "Bạn có thể:\n"
        "- Xem các gói (GO / PLUS / TEAM)\n"
        "- Nhận gói miễn phí thử nghiệm\n"
    )

    await update.message.reply_markdown(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ==============================
# Menu mua gói
# ==============================
async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("GO", callback_data="buy_go")],
        [InlineKeyboardButton("PLUS", callback_data="buy_plus")],
        [InlineKeyboardButton("TEAM", callback_data="buy_team")],
        [InlineKeyboardButton("⬅️ Quay lại", callback_data="back_main")],
    ]

    await update.callback_query.message.edit_text(
        "🛒 **Chọn gói bạn muốn mua:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ==============================
# Nội dung từng gói
# ==============================
async def show_price(update: Update, title, price_main, price_shared):
    text = (
        f"📦 **{title}**\n\n"
        f"💰 Giá chính: `{price_main}`\n"
        f"💳 Giá chia sẻ: `{price_shared}`\n\n"
        "⚠️ Đây là dữ liệu demo."
    )

    await update.callback_query.message.edit_text(text, parse_mode="Markdown")

# ==============================
# Menu miễn phí
# ==============================
async def free_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Miễn phí GO", callback_data="free_go")],
        [InlineKeyboardButton("Miễn phí EDU", callback_data="free_edu")],
        [InlineKeyboardButton("Miễn phí PLUS", callback_data="free_plus")],
        [InlineKeyboardButton("⬅️ Quay lại", callback_data="back_main")],
    ]

    await update.callback_query.message.edit_text(
        "🎁 **Chọn gói miễn phí muốn nhận:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ==============================
# Sản phẩm demo miễn phí
# ==============================
async def free_item(update: Update, name):
    await update.callback_query.message.edit_text(
        f"🎉 Bạn đã nhận **{name}**!\n"
        "Đây chỉ là dữ liệu demo để bạn test bot.\n\n"
        f"`DEMO-{name}-123456`",
        parse_mode="Markdown",
    )

# ==============================
# Xử lý Callback
# ==============================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data

    if data == "buy":
        return await buy_menu(update, context)

    if data == "free":
        return await free_menu(update, context)

    if data == "back_main":
        return await start(update, context)

    if data == "buy_go":
        return await show_price(update, "Gói GO", "100.000đ", "50.000đ")

    if data == "buy_plus":
        return await show_price(update, "Gói PLUS", "200.000đ", "100.000đ")

    if data == "buy_team":
        return await show_price(update, "Gói TEAM", "500.000đ", "250.000đ")

    if data == "free_go":
        return await free_item(update, "GO")

    if data == "free_edu":
        return await free_item(update, "EDU")

    if data == "free_plus":
        return await free_item(update, "PLUS")


# ==============================
# Chạy bot
# ==============================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))

    app.run_polling()


if __name__ == "__main__":
    main()
