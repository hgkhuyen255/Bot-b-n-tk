import os
import json
import time
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

# GIÁ THEO GÓI + LOẠI TÀI KHOẢN
# 👉 SỬA GIÁ TẠI ĐÂY CHO ĐÚNG
PACKAGE_PRICES = {
    "GO": {
        "shop": 50000,    # TK shop cấp
        "own":  70000,    # TK chính chủ
    },
    "PLUS": {
        "shop": 100000,
        "own":  130000,
    },
    "TEAM": {
        "shop": 200000,
        "own":  260000,
    },
    "EDU": {
        "shop": 80000,    # EDU chỉ có shop cấp
    },
}

# Tên file trong Gist
FREE_ACCOUNTS_FILE = "free_accounts.json"    # tk miễn phí
SHOP_ACCOUNTS_FILE = "shop_accounts.json"    # tk bán (shop cấp)
PENDING_ORDERS_FILE = "pending_orders.json"  # đơn chờ thanh toán

# Lưu trạng thái user
# {user_id: {"awaiting_info": "GO|PLUS|TEAM|EDU", "account_type": "shop|own", "payment_code": str}}
USER_STATE = {}

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


def get_and_consume_account(filename: str, package: str) -> str | None:
    """
    Lấy 1 tài khoản từ file (free / shop) theo gói,
    đồng thời xóa tài khoản đó khỏi list để không cấp lại lần sau.
    Cấu trúc file Gist ví dụ:

    {
        "GO": [
            "user1|pass1",
            "user2|pass2"
        ],
        "PLUS": [
            "user3|pass3"
        ]
    }
    """
    data = load_gist_json(filename)
    accounts = data.get(package, [])
    if isinstance(accounts, list) and accounts:
        acc = accounts.pop(0)  # lấy 1 tk, đồng thời remove
        data[package] = accounts
        save_gist_json(filename, data)
        return acc
    return None


def create_pending_order(payment_code: str, user_id: int, chat_id: int,
                         username: str, package: str, account_type: str):
    orders = load_gist_json(PENDING_ORDERS_FILE)
    orders[payment_code] = {
        "user_id": user_id,
        "chat_id": chat_id,
        "username": username,
        "package": package,
        "account_type": account_type,
        "status": "waiting_payment",
        "info": "",
        "created_at": int(time.time())
    }
    save_gist_json(PENDING_ORDERS_FILE, orders)


def update_pending_order_info(payment_code: str, info: str) -> bool:
    orders = load_gist_json(PENDING_ORDERS_FILE)
    if payment_code not in orders:
        return False
    orders[payment_code]["info"] = info
    save_gist_json(PENDING_ORDERS_FILE, orders)
    return True


# ==============================
#  QR HELPER
# ==============================
def generate_qr(package_name: str, account_type: str, user_id: int, username: str | None):
    """
    QR theo gói + loại tài khoản.
    addInfo/payment_code = GO-shop-username
    """
    username_slug = username or f"id{user_id}"

    price = PACKAGE_PRICES[package_name][account_type]
    payment_code = f"{package_name}-{account_type}-{username_slug}"

    qr_url = (
        f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NUMBER}-compact.png"
        f"?amount={price}&addInfo={payment_code}"
    )
    return qr_url, price, payment_code


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


def _package_price_range_label(pkg: str) -> str:
    prices = PACKAGE_PRICES.get(pkg, {})
    vals = list(prices.values())
    if not vals:
        return f"MAIN {pkg}"

    min_p = min(vals)
    max_p = max(vals)
    if min_p == max_p:
        return f"MAIN {pkg} ({min_p}đ)"
    return f"MAIN {pkg} ({min_p}-{max_p}đ)"


def buy_menu_keyboard():
    # Menu mua gói có kèm khoảng giá, ví dụ: MAIN GO (50000-70000đ)
    return {
        "inline_keyboard": [
            [{"text": _package_price_range_label("GO"), "callback_data": "buy_go_main"}],
            [{"text": _package_price_range_label("PLUS"), "callback_data": "buy_plus_main"}],
            [{"text": _package_price_range_label("TEAM"), "callback_data": "buy_team_main"}],
            [{"text": _package_price_range_label("EDU"), "callback_data": "buy_edu_main"}],
            [{"text": "⬅️ Quay lại", "callback_data": "back_main"}],
        ]
    }


def buy_type_keyboard(package: str):
    """
    Menu chọn loại tài khoản (shop cấp / chính chủ) + kèm giá.
    EDU chỉ có shop cấp.
    """
    prices = PACKAGE_PRICES.get(package, {})
    rows = []

    if "shop" in prices:
        rows.append([
            {
                "text": f"TK shop cấp - {prices['shop']}đ",
                "callback_data": f"buy_{package.lower()}_shop",
            }
        ])
    if "own" in prices:
        rows.append([
            {
                "text": f"TK chính chủ - {prices['own']}đ",
                "callback_data": f"buy_{package.lower()}_own",
            }
        ])

    rows.append([{"text": "⬅️ Quay lại chọn gói", "callback_data": "back_buy"}])

    return {"inline_keyboard": rows}


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
        "- Mua gói (GO / PLUS / TEAM / EDU)\n"
        "- Nhận gói miễn phí\n"
        "_Bot mẫu phục vụ học tập._"
    )
    tg_send_message(chat_id, text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")


def send_buy_menu(chat_id, message_id=None):
    text = (
        "🛒 *Chọn gói MAIN bạn muốn mua:*\n\n"
        "Mỗi gói sẽ có 2 lựa chọn:\n"
        "- Tài khoản shop cấp\n"
        "- Tài khoản chính chủ (nếu có)\n\n"
        "Bấm vào gói để xem chi tiết giá."
    )
    if message_id:
        tg_edit_message_text(chat_id, message_id, text,
                             reply_markup=buy_menu_keyboard(), parse_mode="Markdown")
    else:
        tg_send_message(chat_id, text, reply_markup=buy_menu_keyboard(), parse_mode="Markdown")


def send_buy_type_menu(chat_id, package: str, message_id=None):
    prices = PACKAGE_PRICES.get(package, {})
    desc_lines = [f"📦 *GÓI {package}*"]

    if "shop" in prices:
        desc_lines.append(f"- TK shop cấp: `{prices['shop']}đ`")
    if "own" in prices:
        desc_lines.append(f"- TK chính chủ: `{prices['own']}đ`")

    text = "\n".join(desc_lines)

    if message_id:
        tg_edit_message_text(chat_id, message_id, text,
                             reply_markup=buy_type_keyboard(package), parse_mode="Markdown")
    else:
        tg_send_message(chat_id, text,
                        reply_markup=buy_type_keyboard(package), parse_mode="Markdown")


def send_free_menu(chat_id, message_id=None):
    text = (
        "🎁 *Chọn gói miễn phí:*\n\n"
        "Tài khoản miễn phí được cấp tự động từ kho riêng,\n"
        "không ảnh hưởng đến tài khoản shop bán."
    )
    if message_id:
        tg_edit_message_text(chat_id, message_id, text,
                             reply_markup=free_menu_keyboard(), parse_mode="Markdown")
    else:
        tg_send_message(chat_id, text, reply_markup=free_menu_keyboard(), parse_mode="Markdown")


def send_free_item_from_gist(chat_id, package: str, message_id=None):
    """
    Lấy tài khoản miễn phí từ Gist và gửi cho khách.
    """
    account = get_and_consume_account(FREE_ACCOUNTS_FILE, package)
    if account:
        text = (
            f"🎉 Đây là tài khoản *miễn phí {package}* của bạn:\n\n"
            f"`{account}`\n\n"
            "Chúc bạn trải nghiệm vui vẻ!"
        )
    else:
        text = (
            f"❌ Hiện không còn tài khoản miễn phí {package}.\n"
            "Vui lòng thử lại sau hoặc chọn gói khác."
        )

    if message_id:
        tg_edit_message_text(chat_id, message_id, text, parse_mode="Markdown")
    else:
        tg_send_message(chat_id, text, parse_mode="Markdown")


def show_main_package(chat_id, user_id, username, package, account_type, message_id=None):
    """
    Gửi thông tin gói + QR, set trạng thái đợi user gửi email/ghi chú.
    account_type: 'shop' hoặc 'own'
    """
    qr_url, amount, payment_code = generate_qr(package, account_type, user_id, username)

    type_text = "tài khoản shop cấp" if account_type == "shop" else "tài khoản chính chủ"

    text = (
        f"📦 *GÓI MAIN {package} - {type_text}*\n\n"
        "Để kích hoạt gói, vui lòng:\n"
        "1️⃣ Quét mã QR bên dưới để thanh toán.\n"
        "2️⃣ Gửi cho bot *email tài khoản + ghi chú* (nếu có).\n\n"
        f"💳 Số tiền cần thanh toán: `{amount}đ`\n"
        f"🧾 Nội dung chuyển khoản (addInfo): `{payment_code}`\n"
        "⏳ Sau khi hệ thống xác nhận thanh toán, bot sẽ tự động cấp tài khoản / nâng cấp gói."
    )

    if message_id:
        tg_edit_message_text(chat_id, message_id, text, parse_mode="Markdown")
    else:
        tg_send_message(chat_id, text, parse_mode="Markdown")

    tg_send_photo(chat_id, qr_url)

    # lưu trạng thái (gói + loại tk + payment_code)
    USER_STATE[user_id] = {
        "awaiting_info": package,
        "account_type": account_type,
        "payment_code": payment_code,
    }

    # lưu đơn chờ thanh toán vào Gist
    create_pending_order(payment_code, user_id, chat_id, username, package, account_type)


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
        elif data == "back_buy":
            send_buy_menu(chat_id, message_id)

        # CHỌN GÓI
        elif data == "buy_go_main":
            send_buy_type_menu(chat_id, "GO", message_id)
        elif data == "buy_plus_main":
            send_buy_type_menu(chat_id, "PLUS", message_id)
        elif data == "buy_team_main":
            send_buy_type_menu(chat_id, "TEAM", message_id)
        elif data == "buy_edu_main":
            send_buy_type_menu(chat_id, "EDU", message_id)

        # CHỌN LOẠI TÀI KHOẢN (GO)
        elif data == "buy_go_shop":
            show_main_package(chat_id, user_id, username, "GO", "shop", message_id)
        elif data == "buy_go_own":
            show_main_package(chat_id, user_id, username, "GO", "own", message_id)

        # PLUS
        elif data == "buy_plus_shop":
            show_main_package(chat_id, user_id, username, "PLUS", "shop", message_id)
        elif data == "buy_plus_own":
            show_main_package(chat_id, user_id, username, "PLUS", "own", message_id)

        # TEAM
        elif data == "buy_team_shop":
            show_main_package(chat_id, user_id, username, "TEAM", "shop", message_id)
        elif data == "buy_team_own":
            show_main_package(chat_id, user_id, username, "TEAM", "own", message_id)

        # EDU (chỉ shop)
        elif data == "buy_edu_shop":
            show_main_package(chat_id, user_id, username, "EDU", "shop", message_id)

        # FREE ITEMS (lấy từ Gist)
        elif data == "free_go":
            send_free_item_from_gist(chat_id, "GO", message_id)
        elif data == "free_edu":
            send_free_item_from_gist(chat_id, "EDU", message_id)
        elif data == "free_plus":
            send_free_item_from_gist(chat_id, "PLUS", message_id)

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

    # Nếu user đang ở trạng thái "awaiting_info" -> chỉ lưu info, chưa cấp tài khoản
    state = USER_STATE.get(user_id) or {}
    package = state.get("awaiting_info")
    account_type = state.get("account_type")
    payment_code = state.get("payment_code")

    if package and payment_code:
        info = text

        # cập nhật info vào pending_orders.json
        update_pending_order_info(payment_code, info)

        # báo admin: khách đã gửi info, chờ thanh toán
        if ADMIN_CHAT_ID:
            admin_msg = (
                f"📝 *KHÁCH GỬI THÔNG TIN*\n\n"
                f"👤 User: @{username} (ID: {user_id})\n"
                f"📦 Gói: {package} ({account_type})\n"
                f"💳 Mã thanh toán: `{payment_code}`\n"
                f"📩 Thông tin:\n{info}\n\n"
                f"⏳ Đơn đang chờ thanh toán."
            )
            tg_send_message(ADMIN_CHAT_ID, admin_msg, parse_mode="Markdown")

        # báo khách
        tg_send_message(
            chat_id,
            "✅ Đã nhận thông tin của bạn.\n"
            "Khi hệ thống xác nhận thanh toán, bot sẽ tự động xử lý và cấp tài khoản.",
        )

        return PlainTextResponse("OK")

    # Nếu không ở trạng thái mua gói, trả lời hướng dẫn chung
    tg_send_message(
        chat_id,
        "ℹ️ Vui lòng dùng /start để mở menu và chọn gói.",
    )

    return PlainTextResponse("OK")


@app.post("/payment_webhook")
async def payment_webhook(request: Request):
    """
    Webhook để hệ thống thanh toán gọi vào khi giao dịch thành công.
    Body JSON ví dụ:
    {
        "code": "GO-shop-username",
        "amount": 50000
    }
    """
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid_json"}

    payment_code = data.get("code")
    amount = data.get("amount")

    if not payment_code:
        return {"ok": False, "error": "missing_code"}

    orders = load_gist_json(PENDING_ORDERS_FILE)
    order = orders.get(payment_code)
    if not order:
        return {"ok": False, "error": "order_not_found"}

    package = order["package"]
    account_type = order["account_type"]
    user_id = order["user_id"]
    chat_id = order["chat_id"]
    username = order.get("username", "")
    info = order.get("info", "")

    expected_amount = PACKAGE_PRICES[package][account_type]
    if amount is not None and amount != expected_amount:
        # Bạn có thể đổi thành chỉ warning nếu muốn linh hoạt
        return {"ok": False, "error": "amount_mismatch",
                "expected": expected_amount, "got": amount}

    shop_account = None
    if account_type == "shop":
        shop_account = get_and_consume_account(SHOP_ACCOUNTS_FILE, package)

    # lưu đơn đã thanh toán
    save_order_to_gist(
        user_id,
        {
            "username": username,
            "package": package,
            "account_type": account_type,
            "info": info,
            "account_given": shop_account,
            "payment_code": payment_code,
            "amount": amount,
            "status": "paid",
            "paid_at": int(time.time()),
        },
    )

    # xóa khỏi pending
    try:
        del orders[payment_code]
        save_gist_json(PENDING_ORDERS_FILE, orders)
    except Exception as e:
        print("remove pending error:", e)

    # gửi thông báo cho admin
    if ADMIN_CHAT_ID:
        admin_msg = (
            f"💰 *THANH TOÁN THÀNH CÔNG*\n\n"
            f"👤 User: @{username} (ID: {user_id})\n"
            f"📦 Gói: {package} ({account_type})\n"
            f"💳 Mã thanh toán: `{payment_code}`\n"
            f"💵 Số tiền: `{amount}đ`\n"
            f"📩 Thông tin:\n{info or '(không có)'}\n\n"
        )
        if shop_account:
            admin_msg += f"🔐 TK shop cấp: `{shop_account}`"
        else:
            admin_msg += "⚠ Không lấy được tài khoản shop (hết hàng?)."

        tg_send_message(ADMIN_CHAT_ID, admin_msg, parse_mode="Markdown")

    # gửi thông báo cho khách
    if account_type == "shop":
        if shop_account:
            user_msg = (
                "✅ Hệ thống đã xác nhận *thanh toán thành công*.\n\n"
                "Đây là tài khoản shop cấp của bạn:\n"
                f"`{shop_account}`\n\n"
                "Cảm ơn bạn đã sử dụng dịch vụ!"
            )
        else:
            user_msg = (
                "✅ Hệ thống đã xác nhận *thanh toán thành công*.\n"
                "Hiện kho tài khoản đang được cập nhật, admin sẽ cấp tài khoản cho bạn sớm nhất."
            )
    else:  # chính chủ
        user_msg = (
            "✅ Hệ thống đã xác nhận *thanh toán thành công*.\n"
            "Admin sẽ tiến hành nâng cấp / thiết lập gói cho tài khoản chính chủ của bạn."
        )

    tg_send_message(chat_id, user_msg, parse_mode="Markdown")

    return {"ok": True}


@app.get("/")
def home():
    # Endpoint test khi mở trình duyệt
    return {
        "status": "running",
        "webhook_path": WEBHOOK_PATH,
        "webhook_url": WEBHOOK_URL,
    }
