import os
import json
import time
import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

# ==============================
#  ENV & CONFIG
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GIST_ID = os.getenv("GIST_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
CLOUD_RUN_URL = os.getenv("CLOUD_RUN_SERVICE_URL", "")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{CLOUD_RUN_URL}{WEBHOOK_PATH}" if CLOUD_RUN_URL else WEBHOOK_PATH

TG_BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

GIST_URL = f"https://api.github.com/gists/{GIST_ID}"
GIST_HEADERS = {
    "Authorization": f"token {GIST_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Cấu hình VietQR
BANK_ID = "970436"                 # ví dụ: MB Bank
ACCOUNT_NUMBER = "0711000283429"   # THAY bằng STK của bạn

# Giá mỗi gói
PACKAGE_PRICES = {
    "GO":   {"shop": 50000,  "own": 70000},
    "PLUS": {"shop": 100000, "own": 130000},
    "TEAM": {"shop": 200000, "own": 260000},
    "EDU":  {"shop": 80000},  # EDU chỉ shop cấp
}

# File trong Gist
FREE_ACCOUNTS_FILE = "free_accounts.json"
SHOP_ACCOUNTS_FILE = "shop_accounts.json"
PENDING_ORDERS_FILE = "pending_orders.json"

# Trạng thái tạm theo user
# { user_id: {"awaiting_info": package, "account_type": "shop|own", "payment_code": str} }
USER_STATE = {}


# ==============================
#  GIST HELPERS
# ==============================
def load_gist_json(filename: str) -> dict:
    try:
        r = requests.get(GIST_URL, headers=GIST_HEADERS, timeout=10)
        gist = r.json()
        files = gist.get("files", {})
        content = files.get(filename, {}).get("content", "{}")
        return json.loads(content)
    except Exception as e:
        print(f"GIST READ ERR ({filename}):", e)
        return {}


def save_gist_json(filename: str, data: dict) -> None:
    try:
        payload = {
            "files": {
                filename: {
                    "content": json.dumps(data, indent=4, ensure_ascii=False)
                }
            }
        }
        requests.patch(GIST_URL, headers=GIST_HEADERS, json=payload, timeout=10)
    except Exception as e:
        print(f"GIST WRITE ERR ({filename}):", e)


def save_user_to_gist(user_id: int) -> None:
    users = load_gist_json("users.json")
    if str(user_id) not in users:
        users[str(user_id)] = {"joined": True, "joined_at": int(time.time())}
        save_gist_json("users.json", users)


def save_order_to_gist(user_id: int, data: dict) -> None:
    orders = load_gist_json("orders.json")
    orders[str(user_id)] = data
    save_gist_json("orders.json", orders)


def get_and_consume_account(filename: str, package: str) -> str | None:
    """
    Lấy 1 tài khoản từ list theo gói, đồng thời xóa khỏi kho (không cấp trùng).
    Gist file dạng:

    {
      "GO": [
        "user|pass|note",
        "user2|pass2|note"
      ],
      "EDU": [...]
    }
    """
    data = load_gist_json(filename)
    accounts = data.get(package, [])
    if isinstance(accounts, list) and accounts:
        acc = accounts.pop(0)
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
        "created_at": int(time.time()),
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
def generate_qr(package_name: str, account_type: str,
                user_id: int, username: str | None):
    """
    Tạo QR VietQR với addInfo = payment_code
    payment_code = GO-shop-username
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
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("sendMessage error:", e)


def tg_send_photo(chat_id, photo_url, caption=None, parse_mode=None, reply_markup=None):
    url = f"{TG_BASE_URL}/sendPhoto"
    payload = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        payload["caption"] = caption
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("sendPhoto error:", e)


def tg_answer_callback_query(callback_query_id):
    url = f"{TG_BASE_URL}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_query_id}, timeout=10)
    except Exception as e:
        print("answerCallbackQuery error:", e)


def tg_edit_message_text(chat_id, message_id, text, reply_markup=None, parse_mode=None):
    url = f"{TG_BASE_URL}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("editMessageText error:", e)


# ==============================
#  UI KEYBOARDS & MENUS
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
    prices = PACKAGE_PRICES.get(package, {})
    rows = []
    if "shop" in prices:
        rows.append([{
            "text": f"TK shop cấp - {prices['shop']}đ",
            "callback_data": f"buy_{package.lower()}_shop",
        }])
    if "own" in prices:
        rows.append([{
            "text": f"TK chính chủ - {prices['own']}đ",
            "callback_data": f"buy_{package.lower()}_own",
        }])
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


def payment_confirm_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "✅ Tôi đã chuyển khoản", "callback_data": "confirm_paid"}],
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
    Gửi QR + caption + nút 'Tôi đã chuyển khoản' và lưu pending order
    """
    qr_url, amount, payment_code = generate_qr(package, account_type, user_id, username)
    type_text = "tài khoản shop cấp" if account_type == "shop" else "tài khoản chính chủ"
    caption = (
        f"📦 *GÓI MAIN {package} - {type_text}*\n\n"
        "Để kích hoạt gói, vui lòng:\n"
        "1️⃣ Quét mã QR này để thanh toán.\n"
        "2️⃣ Sau khi chuyển khoản, bấm nút *“Tôi đã chuyển khoản”* bên dưới.\n"
        "3️⃣ Gửi cho bot *email tài khoản + ghi chú* (nếu có).\n\n"
        f"💳 Số tiền cần thanh toán: `{amount}đ`\n"
        f"🧾 Nội dung chuyển khoản (addInfo): `{payment_code}`\n"
        "⏳ Khi hệ thống xác nhận thanh toán, bot sẽ tự động cấp tài khoản / nâng cấp gói."
    )
    tg_send_photo(
        chat_id,
        qr_url,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=payment_confirm_keyboard(),
    )
    USER_STATE[user_id] = {
        "awaiting_info": package,
        "account_type": account_type,
        "payment_code": payment_code,
    }
    create_pending_order(payment_code, user_id, chat_id, username, package, account_type)


# ==============================
#  ADMIN HELPERS
# ==============================
def process_paid_order(order: dict, payment_code: str,
                       order_amount: int | None = None,
                       manual: bool = False):
    """
    Dùng chung cho:
    - webhook tự động (/payment_webhook)
    - lệnh admin xác nhận
    """
    package = order["package"]
    account_type = order["account_type"]
    username = order.get("username") or ""
    user_chat_id = order["chat_id"]
    user_id = order["user_id"]
    info = order.get("info", "")
    expected = PACKAGE_PRICES[package][account_type]
    amount = order_amount or expected

    shop_account = None
    if account_type == "shop":
        shop_account = get_and_consume_account(SHOP_ACCOUNTS_FILE, package)

    save_order_to_gist(
        user_id,
        {
            "username": username,
            "package": package,
            "account_type": account_type,
            "payment_code": payment_code,
            "amount": amount,
            "info": info,
            "account_given": shop_account,
            "status": "paid_manual" if manual else "paid",
            "paid_at": int(time.time()),
        },
    )

    orders = load_gist_json(PENDING_ORDERS_FILE)
    if payment_code in orders:
        del orders[payment_code]
        save_gist_json(PENDING_ORDERS_FILE, orders)

    if account_type == "shop":
        if shop_account:
            tg_send_message(
                user_chat_id,
                "🎉 *Thanh toán đã được xác nhận!*\n\n"
                f"Đây là tài khoản của bạn:\n`{shop_account}`",
                parse_mode="Markdown",
            )
        else:
            tg_send_message(
                user_chat_id,
                "⚠ Thanh toán xác nhận, nhưng kho tài khoản shop đang hết.",
            )
    else:
        tg_send_message(
            user_chat_id,
            "🎉 Thanh toán đã xác nhận!\nAdmin sẽ nâng cấp tài khoản chính chủ của bạn.",
            parse_mode="Markdown",
        )

    if ADMIN_CHAT_ID:
        tg_send_message(
            ADMIN_CHAT_ID,
            f"✔ Đơn `{payment_code}` đã được xác nhận.\n"
            f"User: @{username}",
            parse_mode="Markdown",
        )


def handle_admin_confirm(chat_id, user_id, text):
    """
    Các lệnh admin:
    /xacnhan <code>
    /xacnhan_thieu <code> <sotien_da_chuyen>
    /xacnhan_thua <code> <sotien_da_chuyen>
    /xacnhan_khong <code>
    """
    if not ADMIN_CHAT_ID or str(user_id) != str(ADMIN_CHAT_ID):
        tg_send_message(chat_id, "❌ Bạn không phải ADMIN.")
        return

    parts = text.split()
    cmd = parts[0]

    # /xacnhan <payment_code>  → coi như đã thanh toán đủ
    if cmd == "/xacnhan":
        if len(parts) < 2:
            tg_send_message(chat_id, "❗ Dùng: /xacnhan <payment_code>")
            return
        payment_code = parts[1]
        orders = load_gist_json(PENDING_ORDERS_FILE)
        order = orders.get(payment_code)
        if not order:
            tg_send_message(chat_id, "❌ Không tìm thấy đơn.")
            return
        process_paid_order(order, payment_code, manual=True)
        return

    # /xacnhan_thieu <code> <da_chuyen>
    if cmd == "/xacnhan_thieu":
        if len(parts) < 3:
            tg_send_message(chat_id, "❗ Dùng: /xacnhan_thieu <payment_code> <sotien_da_chuyen>")
            return
        payment_code = parts[1]
        try:
            amount = int(parts[2])
        except ValueError:
            tg_send_message(chat_id, "❌ Số tiền không hợp lệ.")
            return
        orders = load_gist_json(PENDING_ORDERS_FILE)
        order = orders.get(payment_code)
        if not order:
            tg_send_message(chat_id, "❌ Không tìm thấy đơn.")
            return
        expected = PACKAGE_PRICES[order["package"]][order["account_type"]]
        missing = expected - amount
        tg_send_message(
            order["chat_id"],
            f"⚠️ Bạn đã *chuyển thiếu* {missing}đ.\n"
            f"Vui lòng chuyển nốt số tiền còn thiếu với nội dung:\n`{payment_code}`",
            parse_mode="Markdown",
        )
        if ADMIN_CHAT_ID:
            tg_send_message(
                ADMIN_CHAT_ID,
                f"⚠️ Đơn `{payment_code}` – KHÁCH CHUYỂN THIẾU {missing}đ.",
                parse_mode="Markdown",
            )
        order["status"] = "underpaid"
        save_gist_json(PENDING_ORDERS_FILE, orders)
        return

    # /xacnhan_thua <code> <da_chuyen>
    if cmd == "/xacnhan_thua":
        if len(parts) < 3:
            tg_send_message(chat_id, "❗ Dùng: /xacnhan_thua <payment_code> <sotien_da_chuyen>")
            return
        payment_code = parts[1]
        try:
            amount = int(parts[2])
        except ValueError:
            tg_send_message(chat_id, "❌ Số tiền không hợp lệ.")
            return
        orders = load_gist_json(PENDING_ORDERS_FILE)
        order = orders.get(payment_code)
        if not order:
            tg_send_message(chat_id, "❌ Không tìm thấy đơn.")
            return
        expected = PACKAGE_PRICES[order["package"]][order["account_type"]]
        over = amount - expected
        tg_send_message(
            order["chat_id"],
            f"ℹ️ Bạn đã *chuyển thừa* {over}đ.\n"
            "Hệ thống vẫn kích hoạt gói như bình thường.",
            parse_mode="Markdown",
        )
        if ADMIN_CHAT_ID:
            tg_send_message(
                ADMIN_CHAT_ID,
                f"ℹ️ Đơn `{payment_code}` – KHÁCH CHUYỂN THỪA {over}đ.",
                parse_mode="Markdown",
            )
        process_paid_order(order, payment_code, order_amount=amount, manual=True)
        return

    # /xacnhan_khong <payment_code>
    if cmd == "/xacnhan_khong":
        if len(parts) < 2:
            tg_send_message(chat_id, "❗ Dùng: /xacnhan_khong <payment_code>")
            return
        payment_code = parts[1]
        orders = load_gist_json(PENDING_ORDERS_FILE)
        order = orders.get(payment_code)
        if not order:
            tg_send_message(chat_id, "❌ Không tìm thấy đơn.")
            return
        tg_send_message(
            order["chat_id"],
            "❌ Hệ thống *không tìm thấy giao dịch* nào theo mã này.\n"
            "Vui lòng kiểm tra lại hoặc thực hiện thanh toán.",
            parse_mode="Markdown",
        )
        if ADMIN_CHAT_ID:
            tg_send_message(
                ADMIN_CHAT_ID,
                f"❌ Đơn `{payment_code}` được đánh dấu KHÔNG THANH TOÁN.",
                parse_mode="Markdown",
            )
        order["status"] = "no_payment"
        save_gist_json(PENDING_ORDERS_FILE, orders)
        return


# ==============================
#  FASTAPI APP & WEBHOOK
# ==============================
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

        # NÚT "Tôi đã chuyển khoản"
        elif data == "confirm_paid":
            state = USER_STATE.get(user_id) or {}
            package = state.get("awaiting_info")
            account_type = state.get("account_type")
            payment_code = state.get("payment_code")

            if not (package and payment_code):
                tg_send_message(
                    chat_id,
                    "❌ Không tìm thấy đơn cần xác nhận.\nVui lòng dùng /start để chọn gói lại.",
                )
                return PlainTextResponse("OK")

            # Cập nhật trạng thái đơn trong pending_orders.json
            orders = load_gist_json(PENDING_ORDERS_FILE)
            if payment_code in orders:
                orders[payment_code]["status"] = "user_confirmed"
                save_gist_json(PENDING_ORDERS_FILE, orders)

            # Báo admin
            if ADMIN_CHAT_ID:
                admin_msg = (
                    "✅ *KHÁCH XÁC NHẬN ĐÃ CHUYỂN KHOẢN*\n\n"
                    f"👤 User: @{username} (ID: {user_id})\n"
                    f"📦 Gói: {package} ({account_type})\n"
                    f"💳 Mã thanh toán: `{payment_code}`\n\n"
                    "⏳ Vui lòng kiểm tra giao dịch trên app ngân hàng / hệ thống thanh toán."
                )
                tg_send_message(ADMIN_CHAT_ID, admin_msg, parse_mode="Markdown")

            # Báo khách
            tg_send_message(
                chat_id,
                "✅ Cảm ơn bạn! Hệ thống sẽ kiểm tra thanh toán và cấp tài khoản sớm nhất.\n"
                "Bạn có thể chờ tin nhắn tiếp theo từ bot.",
            )

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

    # LỆNH ADMIN: /nopay <payment_code>
    if ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID):
        if text.startswith("/nopay "):
            code = text.split(" ", 1)[1].strip()
            orders = load_gist_json(PENDING_ORDERS_FILE)
            order = orders.get(code)
            if not order:
                tg_send_message(chat_id, f"❌ Không tìm thấy đơn với mã: {code}")
                return PlainTextResponse("OK")

            orders[code]["status"] = "no_payment"
            save_gist_json(PENDING_ORDERS_FILE, orders)

            user_chat_id = order["chat_id"]
            expected_amount = PACKAGE_PRICES[order["package"]][order["account_type"]]

            # Báo khách
            tg_send_message(
                user_chat_id,
                "⚠ Hệ thống hiện *chưa thấy giao dịch chuyển khoản* tương ứng với đơn của bạn.\n"
                "Nếu bạn đã chuyển, vui lòng gửi lại hóa đơn/sao kê cho admin để kiểm tra.\n"
                f"Số tiền cần thanh toán cho đơn này là: `{expected_amount}đ`.",
                parse_mode="Markdown",
            )

            # Xác nhận cho admin
            tg_send_message(
                chat_id,
                f"✅ Đã đánh dấu đơn `{code}` là *không thấy tiền* và báo lại cho khách.",
                parse_mode="Markdown",
            )
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
                "📝 *KHÁCH GỬI THÔNG TIN*\n\n"
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
            "Sau khi thanh toán được xác nhận, bot sẽ tự động xử lý và cấp tài khoản.",
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

    Xử lý 4 trạng thái:
    - Chuyển đủ  : cấp tài khoản / nâng cấp
    - Chuyển thừa: vẫn cấp + cảnh báo admin
    - Chuyển thiếu: giữ pending + báo khách + báo admin
    """
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid_json"}

    payment_code = data.get("code")
    amount = data.get("amount")  # số tiền thực tế ngân hàng báo về (int)

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

    # 1) XÁC ĐỊNH TRẠNG THÁI TIỀN
    if amount is None:
        # Không có số tiền thì coi như lỗi payload
        return {
            "ok": False,
            "error": "missing_amount",
            "expected": expected_amount,
        }

    if amount == expected_amount:
        pay_status = "exact"      # chuyển đủ
    elif amount > expected_amount:
        pay_status = "over"       # chuyển thừa
    else:
        pay_status = "under"      # chuyển thiếu

    # 2) CHUYỂN THIẾU → GIỮ PENDING
    if pay_status == "under":
        # Cập nhật trạng thái đơn
        orders[payment_code]["status"] = "underpaid"
        orders[payment_code]["amount"] = amount
        save_gist_json(PENDING_ORDERS_FILE, orders)

        # Báo admin
        if ADMIN_CHAT_ID:
            diff = expected_amount - amount
            admin_msg = (
                "⚠ *KHÁCH CHUYỂN THIẾU TIỀN*\n\n"
                f"👤 User: @{username} (ID: {user_id})\n"
                f"📦 Gói: {package} ({account_type})\n"
                f"💳 Mã thanh toán: `{payment_code}`\n"
                f"💵 Đã chuyển: `{amount}đ` / Cần: `{expected_amount}đ`\n"
                f"❗ Thiếu: `{diff}đ`\n\n"
                "Đơn vẫn được giữ ở trạng thái pending."
            )
            tg_send_message(ADMIN_CHAT_ID, admin_msg, parse_mode="Markdown")

        # Báo khách
        diff = expected_amount - amount
        user_msg = (
            "⚠ *Thanh toán chưa đủ số tiền cần thiết!*\n\n"
            f"Bạn đã chuyển: `{amount}đ`\n"
            f"Số tiền cần thanh toán: `{expected_amount}đ`\n"
            f"Số tiền còn thiếu: `{diff}đ`\n\n"
            "Vui lòng chuyển nốt phần tiền còn thiếu, sau đó bấm lại nút *“Tôi đã chuyển khoản”* "
            "hoặc liên hệ admin nếu cần hỗ trợ."
        )
        tg_send_message(chat_id, user_msg, parse_mode="Markdown")

        return {"ok": True, "status": "underpaid"}

    # 3) CHUYỂN ĐỦ HOẶC THỪA → CẤP
    shop_account = None
    if account_type == "shop":
        shop_account = get_and_consume_account(SHOP_ACCOUNTS_FILE, package)

    # Lưu đơn đã thanh toán (phân biệt exact / overpaid)
    final_status = "paid_exact" if pay_status == "exact" else "paid_over"
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
            "status": final_status,
            "paid_at": int(time.time()),
        },
    )

    # Xóa khỏi pending
    try:
        del orders[payment_code]
        save_gist_json(PENDING_ORDERS_FILE, orders)
    except Exception as e:
        print("remove pending error:", e)

    # ----- THÔNG BÁO ADMIN -----
    if ADMIN_CHAT_ID:
        over_note = ""
        if pay_status == "over":
            diff = amount - expected_amount
            over_note = (
                f"\n⚠ KHÁCH *CHUYỂN THỪA* `{diff}đ` – anh/chị chủ động xử lý hoàn/ghi nhận nhé."
            )

        admin_msg = (
            "💰 *THANH TOÁN THÀNH CÔNG*\n\n"
            f"👤 User: @{username} (ID: {user_id})\n"
            f"📦 Gói: {package} ({account_type})\n"
            f"💳 Mã thanh toán: `{payment_code}`\n"
            f"💵 Số tiền: `{amount}đ` (yêu cầu: `{expected_amount}đ`)\n"
            f"📩 Thông tin:\n{info or '(không có)'}\n\n"
        )
        if shop_account:
            admin_msg += f"🔐 TK shop cấp: `{shop_account}`"
        else:
            if account_type == "shop":
                admin_msg += "⚠ Không lấy được tài khoản shop (hết hàng?)."
            else:
                admin_msg += "🔧 Gói chính chủ – cần admin xử lý nâng cấp tài khoản."

        admin_msg += over_note
        tg_send_message(ADMIN_CHAT_ID, admin_msg, parse_mode="Markdown")

    # ----- THÔNG BÁO KHÁCH -----
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

    # Nếu khách chuyển thừa, nhắc nhẹ
    if pay_status == "over":
        diff = amount - expected_amount
        user_msg += (
            f"\n\nℹ Hệ thống ghi nhận bạn đã chuyển thừa `{diff}đ`. "
            "Admin sẽ hỗ trợ xử lý phần chênh lệch (nếu cần)."
        )

    tg_send_message(chat_id, user_msg, parse_mode="Markdown")

    return {"ok": True, "status": final_status}


@app.get("/")
def home():
    # Endpoint test khi mở trình duyệt
    return {
        "status": "running",
        "webhook_path": WEBHOOK_PATH,
        "webhook_url": WEBHOOK_URL,
    }
