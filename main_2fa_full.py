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
GIST_TOKEN = os.getenv("GIST_TOKEN")  # token GitHub dùng để đọc/ghi Gist
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # chat id admin để nhận đơn
CLOUD_RUN_URL = os.getenv("CLOUD_RUN_SERVICE_URL", "")  # optional

# Đường dẫn webhook trên Cloud Run
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{CLOUD_RUN_URL}{WEBHOOK_PATH}" if CLOUD_RUN_URL else WEBHOOK_PATH

# Gist API
GIST_URL = f"https://api.github.com/gists/{GIST_ID}"

gist_headers = {
    "Authorization": f"token {GIST_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Telegram API base
TG_BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ==============================
#  GIST HELPERS
# ==============================

def load_gist_json(filename: str) -> dict:
    """Đọc 1 file JSON trong Gist, trả về dict (nếu lỗi thì trả {})"""
    try:
        r = requests.get(GIST_URL, headers=gist_headers)
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
        requests.patch(GIST_URL, headers=gist_headers, json=payload)
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
#  TELEGRAM HELPERS
# ==============================

def tg_send_message(chat_id, text, reply_markup=None):
    url = f"{TG_BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("sendMessage error:", e)


def tg_answer_callback_query(callback_query_id):
    url = f"{TG_BASE_URL}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id})
    except Exception as e:
        print("answerCallbackQuery error:", e)


def tg_edit_message_text(chat_id, message_id, text):
    url = f"{TG_BASE_URL}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("editMessageText error:", e)


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

    # 1) Xử lý callback_query (nhấn nút "📦 Mua gói", "🎁 Miễn phí")
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq.get("data", "")
        message = cq.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        message_id = message.get("message_id")
        callback_query_id = cq.get("id")

        # Trả lời callback để Telegram tắt "loading..."
        if callback_query_id:
            tg_answer_callback_query(callback_query_id)

        if data == "buy":
            text = "Bạn muốn mua gói nào?"
        elif data == "free":
            text = "Đây là mục miễn phí!"
        else:
            text = "Tuỳ chọn không hợp lệ."

        if chat_id and message_id:
            tg_edit_message_text(chat_id, message_id, text)

        return PlainTextResponse("OK")

    # 2) Xử lý message bình thường
    message = update.get("message", {})
    if not message:
        # Không phải callback_query cũng không có message -> bỏ qua
        return PlainTextResponse("OK")

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "") or ""
    from_user = message.get("from", {}) or {}

    user_id = from_user.get("id")
    username = from_user.get("username") or ""

    # /start: lưu user + gửi menu
    if text.startswith("/start"):
        if user_id:
            save_user_to_gist(user_id)

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📦 Mua gói", "callback_data": "buy"},
                    {"text": "🎁 Miễn phí", "callback_data": "free"},
                ]
            ]
        }

        welcome_text = (
            "👋 Chào mừng bạn đến với bot!\n\n"
            "👉 Chọn một tuỳ chọn bên dưới:"
        )
        tg_send_message(chat_id, welcome_text, reply_markup=keyboard)
        return PlainTextResponse("OK")

    # Các tin nhắn text khác: coi như thông tin đơn hàng
    if user_id and text.strip():
        order_data = {
            "username": username,
            "user_id": user_id,
            "info": text.strip(),
        }
        save_order_to_gist(user_id, order_data)

        # Gửi thông báo cho admin
        if ADMIN_CHAT_ID:
            admin_msg = (
                "📥 <b>ĐƠN MỚI</b>\n"
                f"👤 Username: <code>{username}</code>\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"ℹ️ Info: <code>{text.strip()}</code>\n"
            )
            tg_send_message(ADMIN_CHAT_ID, admin_msg)

        # Trả lời user
        tg_send_message(chat_id, "✔ Đã ghi nhận thông tin!")
    else:
        # Nếu không có text thì bỏ qua
        tg_send_message(chat_id, "⚠ Vui lòng gửi thông tin dạng text.")

    return PlainTextResponse("OK")


@app.get("/")
def home():
    # Endpoint test khi mở trình duyệt
    return {
        "status": "running",
        "webhook_path": WEBHOOK_PATH,
        "webhook_url": WEBHOOK_URL,
    }
