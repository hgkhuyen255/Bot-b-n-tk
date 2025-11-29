import os
import json
import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

# ==============================
#  ENV
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GIST_ID = os.getenv("GIST_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")  # token GitHub đọc/ghi Gist
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # chat id admin nhận đơn
CLOUD_RUN_URL = os.getenv("CLOUD_RUN_SERVICE_URL", "")  # optional

# Đường dẫn webhook trên Cloud Run
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{CLOUD_RUN_URL}{WEBHOOK_PATH}" if CLOUD_RUN_URL else WEBHOOK_PATH

# Gist API
GIST_URL = f"https://api.github.com/gists/{GIST_ID}"
GIST_HEADERS = {
    "Authorization": f"token {GIST_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Telegram API base
TG_BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==============================
#  CẤU HÌNH QR & GIÁ GÓI
# ==============================
BANK_ID = "970436"                     # MB Bank (ví dụ)
ACCOUNT_NUMBER = "0711000283429"       # 🔥 THAY THÀNH SỐ TK CỦA BẠN

AMOUNTS = {
    "GO": 50000,
    "PLUS": 100000,
    "TEAM": 200000,
}

# Lưu trạng thái user (đợi info gói nào)
USER_STATE = {}  # {user_id: {"awaiting_info": "GO" | "PLUS" | "TEAM"}}


# ==============================
#  GIST HELPERS
# ==============================
def load_gist_json(filename: str) -> dict:
    """Đọc 1 file JSON trong Gist, trả về dict (nếu lỗi thì trả {})"""
    try:
        r = requests.get(GIST_URL, headers=GIST_HEADERS)
        gist = r.json()
        files = gist.get("files", {})
        content = files.get(filename, {}).get("content", "{}")
        return json.loads(content)
    except Exception as e:
        print(f"GIST READ ERR ({filename}):", e)
        return {}


def save_gist_json(filename: str, data: dict) -> None:
    """Ghi 1 dict vào file JSON trong Gist"""
    try:
        payload = {
            "files": {
                filename: {
                    "content": json.dumps(data, indent=4, ensure_ascii=False)
                }
            }
        }
        requests.patch(GIST_URL, headers=GIST_HEADERS, json=payload)
    except Exception as e:
        print(f"GIST WRITE ERR ({filename}):", e)


def save_user_to_gist(user_id: int) -> None:
    users = load_gist_json("users.json")
    if str(user_id) not in users:
        users[str(user_id)] = {"joined": True}
        save_gist_json("users.json", users)


def save_order_to_gist(user_id: int, data: dict) -> None:
    orders = load_gist_json("orders.json")
    orders[str(user_id)] = data
    save_gist_json("orders.json", orders)


# ==============================
#  QR HELPER
# ==============================
def generate_qr(package_name: str, user_id: int, username: str | None):
    # nếu không có username thì dùng id
    username_slug = username or f"id{user_id}"

    addinfo = f"{package_name}-{username_slug}"
    amount = AMOUNTS[package_name]

    qr_url = (
        f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NUMBER}-compact.png"
        f"?amount={amount}&addInfo={addinfo}"
    )
    return qr_url, amount


# ==============================
#  TELEGRAM HELPERS
# ==============================
def tg_send_message(chat_id, text, reply_markup=None, parse_mode=None):
    url = f"{TG_BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("sendMessage error:", e)


def tg_send_photo(chat_id, photo_url, caption=None, parse_mode=None):
    url = f"{TG_BASE_URL}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
    }
    if caption:
        payload["caption"] = caption
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("sendPhoto error:", e)


def tg_answer_callback_query(callback_query_id):
    url = f"{TG_BASE_URL}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id})
    except Exception as e:
        print("answerCallbackQuery error:", e)


def tg_edit_message_text(chat_id, message_id, text, reply_markup=None, parse_mode=None):
    url = f"{TG_BASE_URL}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("editMessageText error:", e)


# ==============================
#  UI: MENU CHÍNH / MUA GÓI / MIỄN PHÍ
# ==============================
def main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🛒 Mua gói", "callback_data": "buy"}],
            [{"text": "🎁 Gói miễn phí", "callback_data": "free"}],
        ]
    }


def buy_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "MAIN GO", "callback_data": "buy_go_main"}],
            [{"text": "MAIN PLUS", "callback_data": "buy_plus_main"}],
            [{"text": "MAIN TEAM", "callback_data": "buy_team_main"}],
            [{"text": "⬅️ Quay lại", "callback_data": "back_main"}],
        ]
    }


def free_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "Miễn phí GO", "callback_data": "free_go"}],
            [{"text": "Miễn phí EDU", "callback_data": "free_edu"}],
            [{"text": "Miễn phí PLUS", "callback_data": "free_plus"}],
            [{"text": "⬅️ Quay lại", "callback_data": "back_main"}],
        ]
    }


def send_main_menu(chat_id):
    text = (
        "🎉 *Chào mừng bạn đến với Bot!*\n\n"
        "Bạn có thể:\n"
        "- Mua gói (GO / PLUS / TEAM)\n"
        "- Nhận gói miễn phí\n"
        "_Bot mẫu phục vụ học tập._"
    )
    tg_send_message(chat_id, text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")


def send_buy_menu(chat_id, message_id=None):
    text = "🛒 *Chọn gói MAIN bạn muốn mua:*"
    if message_id:
        tg_edit_message_text(chat_id, message_id, text,
                             reply_markup=buy_menu_keyboard(), parse_mode="Markdown")
    else:
        tg_send_message(chat_id, text, reply_markup=buy_menu_keyboard(), parse_mode="Markdown")


def send_free_menu(chat_id, message_id=None):
    text = "🎁 *Chọn gói miễn phí:*"
    if message_id:
        tg_edit_message_text(chat_id, message_id, text,
                             reply_markup=free_menu_keyboard(), parse_mode="Markdown")
    else:
        tg_send_message(chat_id, text, reply_markup=free_menu_keyboard(), parse_mode="Markdown")


def send_free_item(chat_id, item_name, message_id=None):
    text = (
        f"🎉 Bạn đã nhận *{item_name}*!\n"
        "Đây là dữ liệu demo.\n\n"
        f"`DEMO-{item_name}-123456`"
    )
    if message_id:
        tg_edit_message_text(chat_id, message_id, text, parse_mode="Markdown")
    else:
        tg_send_message(chat_id, text, parse_mode="Markdown")


def show_main_package(chat_id, user_id, username, package, message_id=None):
    """Gửi thông tin gói + QR, set trạng thái đợi user gửi email/ghi chú"""
    qr_url, amount = generate_qr(package, user_id, username)

    text = (
        f"📦 *GÓI MAIN {package}*\n\n"
        "Để kích hoạt gói, vui lòng gửi:\n"
        "1. Email tài khoản\n"
        "2. Ghi chú (nếu có)\n\n"
        f"💳 Số tiền cần thanh toán: `{amount:,}đ`\n"
        "📌 *Quét mã QR bên dưới để thanh toán.*\n\n"
        "⏳ Vui lòng đợi admin kiểm tra giao dịch."
    )

    # gửi text
    if message_id:
        tg_edit_message_text(chat_id, message_id, text, parse_mode="Markdown")
    else:
        tg_send_message(chat_id, text, parse_mode="Markdown")

    # gửi ảnh QR
    tg_send_photo(chat_id, qr_url)

    # lưu trạng thái
    USER_STATE[user_id] = {"awaiting_info": package}


# ==============================
#      FASTAPI APP
# ==============================

app = FastAPI()


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """
    Webhook nhận update từ Telegram:
    - message        (text, /start, ...)
    - callback_query (nhấn nút inline)
    """
    try:
        update = await request.json()
        print("Incoming update:", update)
    except Exception as e:
        print("Parse update error:", e)
        return PlainTextResponse("OK")

    # 1) Callback query
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq.get("data", "")
        message = cq.get("message", {}) or {}
        chat = message.get("chat", {}) or {}
        chat_id = chat.get("id")
        message_id = message.get("message_id")
        callback_query_id = cq.get("id")

        from_user = cq.get("from", {}) or {}
        user_id = from_user.get("id")
        username = from_user.get("username") or ""

        if callback_query_id:
            tg_answer_callback_query(callback_query_id)

        if not chat_id:
            return PlainTextResponse("OK")

        # MENU CHÍNH / MUA / FREE
        if data == "buy":
            send_buy_menu(chat_id, message_id)
        elif data == "free":
            send_free_menu(chat_id, message_id)
        elif data == "back_main":
            send_main_menu(chat_id)

        # GÓI MAIN
        elif data == "buy_go_main":
            show_main_package(chat_id, user_id, username, "GO", message_id)
        elif data == "buy_plus_main":
            show_main_package(chat_id, user_id, username, "PLUS", message_id)
        elif data == "buy_team_main":
            show_main_package(chat_id, user_id, username, "TEAM", message_id)

        # FREE ITEMS
        elif data == "free_go":
            send_free_item(chat_id, "GO", message_id)
        elif data == "free_edu":
            send_free_item(chat_id, "EDU", message_id)
        elif data == "free_plus":
            send_free_item(chat_id, "PLUS", message_id)

        return PlainTextResponse("OK")

    # 2) Message thường
    message = update.get("message", {}) or {}
    if not message:
        return PlainTextResponse("OK")

    chat = message.get("chat", {}) or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    from_user = message.get("from", {}) or {}
    user_id = from_user.get("id")
    username = from_user.get("username") or ""

    if not chat_id or not user_id:
        return PlainTextResponse("OK")

    # /start: lưu user + gửi menu
    if text.startswith("/start"):
        save_user_to_gist(user_id)
        send_main_menu(chat_id)
        return PlainTextResponse("OK")

    # Nếu user đang ở trạng thái "awaiting_info" -> xử lý như receive_user_info
    state = USER_STATE.get(user_id) or {}
    package = state.get("awaiting_info")
    if package:
        info = text

        save_order_to_gist(
            user_id,
            {
                "username": username,
                "package": package,
                "info": info,
            },
        )

        # Gửi admin
        if ADMIN_CHAT_ID:
            admin_msg = (
                f"🔥 *ĐƠN HÀNG MỚI*\n\n"
                f"👤 User: @{username} (ID: {user_id})\n"
                f"📦 Gói: {package}\n"
                f"📩 Thông tin:\n{info}"
            )
            tg_send_message(ADMIN_CHAT_ID, admin_msg, parse_mode="Markdown")

        # Báo khách
        tg_send_message(
            chat_id,
            "✅ Thông tin đã được ghi nhận.\nAdmin sẽ hỗ trợ bạn sớm!",
        )

        # reset state
        USER_STATE[user_id]["awaiting_info"] = None
        return PlainTextResponse("OK")

    # Nếu không ở trạng thái mua gói, có thể trả lời hướng dẫn chung
    tg_send_message(
        chat_id,
        "ℹ️ Vui lòng dùng /start để mở menu và chọn gói.",
    )

    return PlainTextResponse("OK")


@app.get("/")
def home():
    # Endpoint test khi mở trình duyệt
    return {
        "status": "running",
        "webhook_path": WEBHOOK_PATH,
        "webhook_url": WEBHOOK_URL,
    }
