import os
import json
import time
import hmac
import hashlib
import urllib.parse
import requests
from typing import Any
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse

# ==============================
#  ENV & CONFIG
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GIST_ID = os.getenv("GIST_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")

# Có thể dùng env hoặc giữ mặc định 5816758036
_admin_env = os.getenv("ADMIN_CHAT_ID")
if _admin_env:
    try:
        ADMIN_CHAT_ID = int(_admin_env)
    except ValueError:
        ADMIN_CHAT_ID = 5816758036
else:
    ADMIN_CHAT_ID = 5816758036

CLOUD_RUN_URL = os.getenv("CLOUD_RUN_SERVICE_URL", "")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{CLOUD_RUN_URL}{WEBHOOK_PATH}" if CLOUD_RUN_URL else WEBHOOK_PATH

TG_BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

GIST_URL = f"https://api.github.com/gists/{GIST_ID}"
GIST_HEADERS = {
    "Authorization": f"token {GIST_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# Cấu hình payOS / fallback QR
PAYOS_CLIENT_ID = os.getenv("PAYOS_CLIENT_ID", "")
PAYOS_API_KEY = os.getenv("PAYOS_API_KEY", "")
PAYOS_CHECKSUM_KEY = os.getenv("PAYOS_CHECKSUM_KEY", "")
PAYOS_BASE_URL = os.getenv("PAYOS_BASE_URL", "https://api-merchant.payos.vn")
PAYOS_RETURN_URL = os.getenv("PAYOS_RETURN_URL", f"{CLOUD_RUN_URL}/payos-return" if CLOUD_RUN_URL else "")
PAYOS_CANCEL_URL = os.getenv("PAYOS_CANCEL_URL", f"{CLOUD_RUN_URL}/payos-cancel" if CLOUD_RUN_URL else "")
PAYOS_WEBHOOK_PATH = os.getenv("PAYOS_WEBHOOK_PATH", "/payos-webhook")
PAYOS_WEBHOOK_URL = f"{CLOUD_RUN_URL}{PAYOS_WEBHOOK_PATH}" if CLOUD_RUN_URL else ""

BANK_ID = os.getenv("BANK_ID", "970436")
ACCOUNT_NUMBER = os.getenv("ACCOUNT_NUMBER", "0711000283429")
# Giá mỗi gói
PACKAGE_PRICES = {
    "GO":   {"shop": 300000,  "own": 300000},
    "PLUS": {"shop": 50000, "own": 100000},
    "TEAM": {"shop": 180000, "own": 200000},
    "EDU":  {"shop": 500000},  # EDU chỉ shop cấp
}

# File trong Gist
FREE_ACCOUNTS_FILE = "free_accounts.json"
SHOP_ACCOUNTS_FILE = "shop_accounts.json"
PENDING_ORDERS_FILE = "pending_orders.json"
PAID_ORDERS_FILE = "paid_orders.json"
FREE_CLAIMS_FILE = "free_claims.json"
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
    user_key = str(user_id)
    user_orders = orders.get(user_key, [])
    if isinstance(user_orders, dict):
        user_orders = [user_orders]
    user_orders.append(data)
    orders[user_key] = user_orders
    save_gist_json("orders.json", orders)
def has_claimed_free(user_id: int, package: str) -> bool:
    """
    Kiểm tra user đã nhận tài khoản miễn phí / khuyến mãi của loại này chưa.
    package: tên gói - ví dụ: "GO", "EDU", "PLUS", "CANVA_EDU", ...
    """
    claims = load_gist_json(FREE_CLAIMS_FILE)
    u = claims.get(str(user_id), {})
    return u.get(package, False)


def mark_claimed_free(user_id: int, package: str) -> None:
    """
    Đánh dấu user đã nhận 1 tài khoản miễn phí / khuyến mãi của loại này.
    """
    claims = load_gist_json(FREE_CLAIMS_FILE)
    u = claims.get(str(user_id), {})
    u[package] = True
    claims[str(user_id)] = u
    save_gist_json(FREE_CLAIMS_FILE, claims)


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
#  PAYMENT / payOS HELPERS
# ==============================
def to_compact_slug(value: str) -> str:
    safe = ''.join(ch for ch in (value or '') if ch.isalnum())
    return (safe[:12] or 'guest').upper()


def build_payment_code(package_name: str, account_type: str, user_id: int, username: str | None) -> str:
    username_slug = to_compact_slug(username or f"ID{user_id}")
    return f"{package_name}-{account_type}-{username_slug}-{int(time.time())}"


def build_payos_order_code() -> int:
    return int(time.time() * 1000) % 900000000000 + 100000000000


def sign_payos_payment_request(amount: int, order_code: int, description: str, cancel_url: str, return_url: str) -> str:
    raw = (
        f"amount={amount}"
        f"&cancelUrl={cancel_url}"
        f"&description={description}"
        f"&orderCode={order_code}"
        f"&returnUrl={return_url}"
    )
    return hmac.new(PAYOS_CHECKSUM_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()


def deep_sort_data(obj: Any):
    if isinstance(obj, dict):
        return {k: deep_sort_data(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [deep_sort_data(item) for item in obj]
    return obj


def flatten_signature_data(data: Any, prefix: str = "") -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if isinstance(data, dict):
        for key in sorted(data.keys()):
            new_prefix = f"{prefix}.{key}" if prefix else key
            pairs.extend(flatten_signature_data(data[key], new_prefix))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            new_prefix = f"{prefix}[{idx}]"
            pairs.extend(flatten_signature_data(item, new_prefix))
    else:
        if data is None:
            value = ""
        elif isinstance(data, bool):
            value = "true" if data else "false"
        else:
            value = str(data)
        pairs.append((prefix, value))
    return pairs


def verify_payos_webhook_signature(payload: dict) -> bool:
    signature = payload.get("signature")
    data = payload.get("data")
    if not signature or data is None or not PAYOS_CHECKSUM_KEY:
        return False
    sorted_data = deep_sort_data(data)
    pairs = flatten_signature_data(sorted_data)
    raw = "&".join(f"{k}={v}" for k, v in pairs)
    expected = hmac.new(PAYOS_CHECKSUM_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def generate_fallback_qr(amount: int, payment_code: str):
    qr_url = (
        f"https://img.vietqr.io/image/{BANK_ID}-{ACCOUNT_NUMBER}-compact2.png"
        f"?amount={amount}&addInfo={urllib.parse.quote(payment_code)}"
    )
    return qr_url


def payos_headers() -> dict:
    return {
        "x-client-id": PAYOS_CLIENT_ID,
        "x-api-key": PAYOS_API_KEY,
        "Content-Type": "application/json",
    }


def create_payos_payment_link(package_name: str, account_type: str, user_id: int, username: str | None):
    amount = PACKAGE_PRICES[package_name][account_type]
    payment_code = build_payment_code(package_name, account_type, user_id, username)
    order_code = build_payos_order_code()
    description = payment_code[:25]

    fallback_qr = generate_fallback_qr(amount, payment_code)
    result = {
        "payment_code": payment_code,
        "order_code": order_code,
        "amount": amount,
        "checkout_url": "",
        "qr_image_url": fallback_qr,
        "qr_code": "",
        "provider": "fallback",
        "description": description,
    }

    if not (PAYOS_CLIENT_ID and PAYOS_API_KEY and PAYOS_CHECKSUM_KEY and PAYOS_RETURN_URL and PAYOS_CANCEL_URL):
        return result

    payload = {
        "orderCode": order_code,
        "amount": amount,
        "description": description,
        "items": [{
            "name": f"{package_name}-{account_type}",
            "quantity": 1,
            "price": amount,
        }],
        "cancelUrl": PAYOS_CANCEL_URL,
        "returnUrl": PAYOS_RETURN_URL,
    }
    payload["signature"] = sign_payos_payment_request(amount, order_code, description, PAYOS_CANCEL_URL, PAYOS_RETURN_URL)

    try:
        r = requests.post(f"{PAYOS_BASE_URL}/v2/payment-requests", headers=payos_headers(), json=payload, timeout=20)
        data = r.json()
        if r.ok and str(data.get("code")) == "00" and data.get("data"):
            info = data["data"]
            qr_raw = info.get("qrCode") or ""
            qr_img = f"https://api.qrserver.com/v1/create-qr-code/?size=512x512&data={urllib.parse.quote(qr_raw)}" if qr_raw else fallback_qr
            result.update({
                "checkout_url": info.get("checkoutUrl", ""),
                "qr_image_url": qr_img,
                "qr_code": qr_raw,
                "provider": "payos",
                "payment_link_id": info.get("paymentLinkId", ""),
            })
    except Exception as e:
        print("create_payos_payment_link error:", e)

    return result


def create_pending_order(payment_code: str, user_id: int, chat_id: int,
                         username: str, package: str, account_type: str,
                         amount: int | None = None, order_code: int | None = None,
                         checkout_url: str = "", qr_image_url: str = "",
                         provider: str = "fallback"):
    orders = load_gist_json(PENDING_ORDERS_FILE)
    orders[payment_code] = {
        "user_id": user_id,
        "chat_id": chat_id,
        "username": username,
        "package": package,
        "account_type": account_type,
        "status": "waiting_payment",
        "delivery_status": "pending",
        "info": "",
        "created_at": int(time.time()),
        "amount": amount,
        "order_code": order_code,
        "checkout_url": checkout_url,
        "qr_image_url": qr_image_url,
        "provider": provider,
        "last_check_at": 0,
    }
    save_gist_json(PENDING_ORDERS_FILE, orders)


def find_pending_order_by_order_code(order_code: int | str):
    orders = load_gist_json(PENDING_ORDERS_FILE)
    order_code_str = str(order_code)
    for payment_code, order in orders.items():
        if str(order.get("order_code")) == order_code_str:
            return payment_code, order, orders
    return None, None, orders


def mark_paid_order(payment_code: str, order: dict, *, amount: int, transaction_ref: str = "", source: str = "payos_webhook"):
    paid = load_gist_json(PAID_ORDERS_FILE)
    paid[payment_code] = {
        **order,
        "status": "paid",
        "delivery_status": order.get("delivery_status", "pending"),
        "paid_at": int(time.time()),
        "paid_amount": amount,
        "transaction_ref": transaction_ref,
        "paid_source": source,
    }
    save_gist_json(PAID_ORDERS_FILE, paid)


def get_paid_order(payment_code: str):
    paid = load_gist_json(PAID_ORDERS_FILE)
    return paid.get(payment_code)


def get_payos_payment_status(order_code: int | str):
    if not (PAYOS_CLIENT_ID and PAYOS_API_KEY):
        return {"ok": False, "error": "payos_not_configured"}
    try:
        r = requests.get(f"{PAYOS_BASE_URL}/v2/payment-requests/{order_code}", headers=payos_headers(), timeout=20)
        data = r.json()
        if not r.ok:
            return {"ok": False, "error": data}
        return {"ok": True, "data": data.get("data") or {}}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def confirm_payos_webhook_url():
    if not (PAYOS_CLIENT_ID and PAYOS_API_KEY and PAYOS_WEBHOOK_URL):
        print("Skip payOS confirm webhook: missing env")
        return
    try:
        r = requests.post(
            f"{PAYOS_BASE_URL}/confirm-webhook",
            headers=payos_headers(),
            json={"webhookUrl": PAYOS_WEBHOOK_URL},
            timeout=20,
        )
        print("payOS confirm-webhook:", r.status_code, r.text)
    except Exception as e:
        print("payOS confirm-webhook error:", e)

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
        r = requests.post(url, json=payload, timeout=10)
        # LOG để kiểm tra việc gửi tin
        print("TG sendMessage:", payload, "→", r.status_code, r.text)
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
        r = requests.post(url, json=payload, timeout=10)
        print("TG sendPhoto:", payload, "→", r.status_code, r.text)
    except Exception as e:
        print("sendPhoto error:", e)


def tg_answer_callback_query(callback_query_id):
    url = f"{TG_BASE_URL}/answerCallbackQuery"
    try:
        r = requests.post(url, json={"callback_query_id": callback_query_id}, timeout=10)
        print("TG answerCallbackQuery:", r.status_code, r.text)
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
        r = requests.post(url, json=payload, timeout=10)
        print("TG editMessageText:", payload, "→", r.status_code, r.text)
    except Exception as e:
        print("editMessageText error:", e)


def send_admin_message(text: str, reply_markup=None):
    """
    Gửi tin nhắn cho admin.
    Không dùng Markdown để tránh lỗi parse (username có dấu _ , v.v.).
    Có thể đính kèm inline keyboard qua reply_markup.
    """
    if not ADMIN_CHAT_ID:
        print("ADMIN_CHAT_ID not set, skip admin message:", text)
        return
    tg_send_message(ADMIN_CHAT_ID, text, reply_markup=reply_markup, parse_mode=None)



# ==============================
#  UI KEYBOARDS & MENUS
# ==============================
def main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🛒 Mua tài khoản", "callback_data": "buy"}],
            [{"text": "🎁 Tài khoản dùng thử miễn phí", "callback_data": "free"}],
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
            [{"text": _package_price_range_label("ChatGPT GO gói 1 năm"), "callback_data": "buy_go_main"}],
            [{"text": _package_price_range_label("ChatGPT PLUS gói 1 tháng"), "callback_data": "buy_plus_main"}],
            [{"text": _package_price_range_label("ChatGPT TEAM gói 1 tháng"), "callback_data": "buy_team_main"}],
            [{"text": _package_price_range_label("ChatGPT EDU gói gần 2 năm"), "callback_data": "buy_edu_main"}],
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
            [{"text": "Free ChatgptGO", "callback_data": "free_go"}],
            [{"text": "Free ChatgptEDU", "callback_data": "free_edu"}],
            [{"text": "Free ChatgptPLUS", "callback_data": "free_plus"}],
            [{"text": "Free Canva EDU", "callback_data": "free_canva_edu"}],   # ← THÊM
            [{"text": "⬅️ Quay lại", "callback_data": "back_main"}],
        ]
    }




def payment_confirm_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "✅ Tôi đã chuyển khoản", "callback_data": "confirm_paid"}],
            [{"text": "🔄 Kiểm tra trạng thái", "callback_data": "check_payment_status"}],
        ]
    }

def admin_order_keyboard(payment_code: str):
    """
    Inline keyboard cho admin xử lý đơn theo payment_code.
    """
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Đủ tiền", "callback_data": f"adm_ok|{payment_code}"},
            ],
            [
                {"text": "⚠️ Chuyển thiếu", "callback_data": f"adm_under|{payment_code}"},
                {"text": "💸 Chuyển thừa", "callback_data": f"adm_over|{payment_code}"},
            ],
            [
                {"text": "❌ Không thấy tiền", "callback_data": f"adm_none|{payment_code}"},
            ],
        ]
    }

def send_main_menu(chat_id):
    text = (
        "🎉 Chào mừng bạn đến với Trạm tài khoản số\n\n"
        "TK - Shop zalo: 0849289899\n"
        "- Mua tài khoản (ChatgptGO / ChatgptPLUS / ChatgtTEAM / ChatgptEDU)\n"
        "- Nhận tài khoản miễn phí\n"
        "- Quy trình tự động, thao tác đơn giản.\n"
        "Chọn nút bên dưới để sử dụng các chức năng\n"
        "Nếu gặp vấn đề trong quá trình mua gói và sử dụng có thể liên hệ trực tiếp admin"
    )
    tg_send_message(chat_id, text, reply_markup=main_menu_keyboard())


def send_buy_menu(chat_id, message_id=None):
    text = (
        "🛒 Chọn gói chatgpt bạn muốn mua:\n\n"
        "Mỗi gói sẽ có 2 lựa chọn:\n"
        "- Tài khoản shop cấp\n"
        "- Tài khoản chính chủ (nếu có)\n\n"
        "Bấm vào gói để xem chi tiết giá.\n"
        "Để mua nhanh hơn vui lòng liên hệ admin hoặc zalo cho shop."
    )
    if message_id:
        tg_edit_message_text(chat_id, message_id, text, reply_markup=buy_menu_keyboard())
    else:
        tg_send_message(chat_id, text, reply_markup=buy_menu_keyboard())


def send_buy_type_menu(chat_id, package: str, message_id=None):
    prices = PACKAGE_PRICES.get(package, {})
    desc_lines = [f"📦 GÓI {package}"]
    if "shop" in prices:
        desc_lines.append(f"- TK shop cấp: {prices['shop']}đ")
    if "own" in prices:
        desc_lines.append(f"- TK chính chủ: {prices['own']}đ")
    text = "\n".join(desc_lines)
    if message_id:
        tg_edit_message_text(chat_id, message_id, text,
                             reply_markup=buy_type_keyboard(package))
    else:
        tg_send_message(chat_id, text, reply_markup=buy_type_keyboard(package))


def send_free_menu(chat_id, message_id=None):
    text = (
        "🎁 Chọn gói miễn phí:\n\n"
        "Tài khoản miễn phí được cấp tự động từ kho riêng,\n"
        "không ảnh hưởng đến tài khoản shop bán.\n"
        "Có giới hạn nhận tài khoản miễn phí."
    )
    if message_id:
        tg_edit_message_text(chat_id, message_id, text,
                             reply_markup=free_menu_keyboard())
    else:
        tg_send_message(chat_id, text, reply_markup=free_menu_keyboard())


def send_free_item_from_gist(chat_id, user_id, package: str, message_id=None):
    """
    Cấp tài khoản miễn phí / khuyến mãi cho user.
    Mỗi user chỉ được nhận 1 lần cho mỗi loại package.
    """
    # Nếu user đã nhận loại này rồi → từ chối
    if has_claimed_free(user_id, package):
        text = (
            f"❌ Bạn đã nhận tài khoản miễn phí / khuyến mãi loại {package} trước đó.\n"
            "Mỗi loại tài khoản chỉ được nhận 1 lần cho mỗi người dùng."
        )
        if message_id:
            tg_edit_message_text(chat_id, message_id, text)
        else:
            tg_send_message(chat_id, text)
        return

    # Lấy tài khoản từ kho
    account = get_and_consume_account(FREE_ACCOUNTS_FILE, package)
    if account:
        # Đánh dấu đã nhận loại này
        mark_claimed_free(user_id, package)
        text = (
            f"🎉 Đây là tài khoản miễn phí {package} của bạn:\n\n"
            f"{account}\n\n"
            "Chúc bạn trải nghiệm vui vẻ!"
        )
    else:
        text = (
            f"❌ Hiện không còn tài khoản miễn phí {package}.\n"
            "Vui lòng thử lại sau hoặc chọn gói khác."
        )

    if message_id:
        tg_edit_message_text(chat_id, message_id, text)
    else:
        tg_send_message(chat_id, text)



def show_main_package(chat_id, user_id, username, package, account_type, message_id=None):
    """
    Tạo đơn payOS riêng cho từng giao dịch, có checkout link + QR riêng.
    """
    payment = create_payos_payment_link(package, account_type, user_id, username)
    amount = payment["amount"]
    payment_code = payment["payment_code"]
    order_code = payment["order_code"]
    checkout_url = payment.get("checkout_url", "")
    qr_url = payment.get("qr_image_url", "")
    provider = payment.get("provider", "fallback")

    type_text = "tài khoản shop cấp" if account_type == "shop" else "tài khoản chính chủ"
    caption = (
        f"📦 GÓI MAIN {package} - {type_text}\n\n"
        f"💳 Số tiền cần thanh toán: {amount}đ\n"
        f"🧾 Mã đơn: {payment_code}\n"
        f"🔢 orderCode: {order_code}\n"
        f"🏦 Cổng thanh toán: {'payOS' if provider == 'payos' else 'QR dự phòng'}\n\n"
        "1️⃣ Quét QR hoặc mở link thanh toán riêng của đơn này.\n"
        "2️⃣ Khi payOS báo thành công, bot sẽ tự giao hàng.\n"
        "3️⃣ Nếu webhook đến chậm, bấm ‘Kiểm tra trạng thái’ để đồng bộ thủ công.\n"
        "4️⃣ Bạn vẫn có thể gửi email/tài khoản cần nâng cấp cho bot như cũ."
    )
    if checkout_url:
        caption += f"\n\n🔗 Link thanh toán: {checkout_url}"

    tg_send_photo(chat_id, qr_url, caption=caption, reply_markup=payment_confirm_keyboard())
    USER_STATE[user_id] = {
        "awaiting_info": package,
        "account_type": account_type,
        "payment_code": payment_code,
        "order_code": order_code,
    }
    create_pending_order(
        payment_code,
        user_id,
        chat_id,
        username,
        package,
        account_type,
        amount=amount,
        order_code=order_code,
        checkout_url=checkout_url,
        qr_image_url=qr_url,
        provider=provider,
    )


# ==============================
#  ADMIN HELPERS
# ==============================
def process_paid_order(order: dict, payment_code: str,
                       order_amount: int | None = None,
                       manual: bool = False,
                       transaction_ref: str = ""):
    """
    Dùng chung cho webhook tự động, check trạng thái thủ công và admin xác nhận.
    Chống giao trùng nếu webhook gửi lặp lại.
    """
    if order.get("delivery_status") == "delivered":
        return {"ok": True, "status": "already_delivered"}

    paid_order = get_paid_order(payment_code)
    if paid_order and paid_order.get("delivery_status") == "delivered":
        return {"ok": True, "status": "already_delivered"}

    package = order["package"]
    account_type = order["account_type"]
    username = order.get("username") or ""
    user_chat_id = order["chat_id"]
    user_id = order["user_id"]
    info = order.get("info", "")
    expected = PACKAGE_PRICES[package][account_type]
    amount = order_amount or expected

    shop_account = order.get("account_given")
    if account_type == "shop" and not shop_account:
        shop_account = get_and_consume_account(SHOP_ACCOUNTS_FILE, package)

    order["delivery_status"] = "delivered"
    order["account_given"] = shop_account
    order["status"] = "paid_manual" if manual else "paid"

    save_order_to_gist(
        user_id,
        {
            "username": username,
            "package": package,
            "account_type": account_type,
            "payment_code": payment_code,
            "order_code": order.get("order_code"),
            "amount": amount,
            "info": info,
            "account_given": shop_account,
            "status": order["status"],
            "paid_at": int(time.time()),
            "transaction_ref": transaction_ref,
        },
    )
    mark_paid_order(payment_code, order, amount=amount, transaction_ref=transaction_ref, source="manual" if manual else "payos")

    orders = load_gist_json(PENDING_ORDERS_FILE)
    if payment_code in orders:
        orders[payment_code]["delivery_status"] = "delivered"
        orders[payment_code]["status"] = order["status"]
        orders[payment_code]["account_given"] = shop_account
        save_gist_json(PENDING_ORDERS_FILE, orders)

    if account_type == "shop":
        if shop_account:
            tg_send_message(
                user_chat_id,
                "🎉 Thanh toán đã được xác nhận!\n\n"
                f"Đây là tài khoản của bạn:\n{shop_account}",
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
        )

    send_admin_message(
        f"✔ Đơn {payment_code} đã được xử lý {'thủ công' if manual else 'tự động'} cho @{username}"
    )
    return {"ok": True, "status": order["status"]}


def sync_order_status_for_user(user_id: int):
    state = USER_STATE.get(user_id) or {}
    payment_code = state.get("payment_code")
    order_code = state.get("order_code")
    if not payment_code or not order_code:
        return {"ok": False, "message": "Không tìm thấy đơn đang chờ của bạn."}

    orders = load_gist_json(PENDING_ORDERS_FILE)
    order = orders.get(payment_code)
    if not order:
        paid = get_paid_order(payment_code)
        if paid and paid.get("delivery_status") == "delivered":
            return {"ok": True, "message": "Đơn này đã thanh toán và đã giao trước đó."}
        return {"ok": False, "message": "Đơn không còn trong danh sách chờ."}

    if order.get("delivery_status") == "delivered":
        return {"ok": True, "message": "Đơn này đã được giao rồi."}

    status_resp = get_payos_payment_status(order_code)
    if not status_resp.get("ok"):
        return {"ok": False, "message": f"Không kiểm tra được payOS: {status_resp.get('error')}"}

    data = status_resp.get("data") or {}
    status = str(data.get("status") or "").upper()
    amount_paid = int(data.get("amountPaid") or 0)
    order["last_check_at"] = int(time.time())
    order["payos_status"] = status
    orders[payment_code] = order
    save_gist_json(PENDING_ORDERS_FILE, orders)

    expected = PACKAGE_PRICES[order["package"]][order["account_type"]]
    if status == "PAID" or amount_paid >= expected:
        process_paid_order(order, payment_code, order_amount=max(amount_paid, expected), manual=False, transaction_ref="manual_status_sync")
        return {"ok": True, "message": "Thanh toán đã thành công. Bot đã tự xử lý giao hàng."}

    if status == "CANCELLED":
        order["status"] = "cancelled"
        orders[payment_code] = order
        save_gist_json(PENDING_ORDERS_FILE, orders)
        return {"ok": False, "message": "Đơn này đã bị hủy trên payOS."}

    return {"ok": True, "message": f"payOS hiện báo trạng thái: {status or 'PENDING'}. Đơn vẫn đang chờ thanh toán."}


def handle_admin_confirm(chat_id, user_id, text):
    """
    Các lệnh admin:
    /xacnhan <code>
    /xacnhan_thieu <code> <sotien_da_chuyen>
    /xacnhan_thua <code> <sotien_da_chuyen>
    /xacnhan_khong <code>
    """
    if not ADMIN_CHAT_ID or user_id != ADMIN_CHAT_ID:
        tg_send_message(chat_id, "❌ Bạn không phải ADMIN.")
        return

    parts = text.split()
    cmd = parts[0]

    if cmd == "/xacnhan":
        if len(parts) < 2:
            tg_send_message(chat_id, "Dùng: /xacnhan <payment_code>")
            return
        payment_code = parts[1]
        orders = load_gist_json(PENDING_ORDERS_FILE)
        order = orders.get(payment_code)
        if not order:
            tg_send_message(chat_id, "Không tìm thấy đơn.")
            return
        process_paid_order(order, payment_code, manual=True)
        return

    if cmd == "/xacnhan_thieu":
        if len(parts) < 3:
            tg_send_message(chat_id, "Dùng: /xacnhan_thieu <payment_code> <sotien_da_chuyen>")
            return
        payment_code = parts[1]
        try:
            amount = int(parts[2])
        except ValueError:
            tg_send_message(chat_id, "Số tiền không hợp lệ.")
            return
        orders = load_gist_json(PENDING_ORDERS_FILE)
        order = orders.get(payment_code)
        if not order:
            tg_send_message(chat_id, "Không tìm thấy đơn.")
            return
        expected = PACKAGE_PRICES[order["package"]][order["account_type"]]
        missing = expected - amount
        tg_send_message(order["chat_id"], f"Bạn đã chuyển thiếu {missing}đ. Vui lòng chuyển nốt cho đơn: {payment_code}")
        order["status"] = "underpaid"
        order["amount"] = amount
        orders[payment_code] = order
        save_gist_json(PENDING_ORDERS_FILE, orders)
        send_admin_message(f"Đơn {payment_code} – khách chuyển thiếu {missing}đ.")
        return

    if cmd == "/xacnhan_thua":
        if len(parts) < 3:
            tg_send_message(chat_id, "Dùng: /xacnhan_thua <payment_code> <sotien_da_chuyen>")
            return
        payment_code = parts[1]
        try:
            amount = int(parts[2])
        except ValueError:
            tg_send_message(chat_id, "Số tiền không hợp lệ.")
            return
        orders = load_gist_json(PENDING_ORDERS_FILE)
        order = orders.get(payment_code)
        if not order:
            tg_send_message(chat_id, "Không tìm thấy đơn.")
            return
        process_paid_order(order, payment_code, order_amount=amount, manual=True)
        return

    if cmd == "/xacnhan_khong":
        if len(parts) < 2:
            tg_send_message(chat_id, "Dùng: /xacnhan_khong <payment_code>")
            return
        payment_code = parts[1]
        orders = load_gist_json(PENDING_ORDERS_FILE)
        order = orders.get(payment_code)
        if not order:
            tg_send_message(chat_id, "Không tìm thấy đơn.")
            return
        order["status"] = "no_payment"
        orders[payment_code] = order
        save_gist_json(PENDING_ORDERS_FILE, orders)
        tg_send_message(order["chat_id"], "Hệ thống chưa thấy giao dịch cho đơn này. Nếu bạn đã chuyển, vui lòng liên hệ admin.")
        send_admin_message(f"Đơn {payment_code} được đánh dấu KHÔNG THANH TOÁN.")
        return


# ==============================
#  FASTAPI APP & WEBHOOK
# ==============================
app = FastAPI()


@app.on_event("startup")
def on_startup():
    confirm_payos_webhook_url()


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
        print("Incoming update:", update)
    except Exception as e:
        print("Parse update error:", e)
        return PlainTextResponse("OK")

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

        if data == "buy":
            send_buy_menu(chat_id, message_id)
        elif data == "free":
            send_free_menu(chat_id, message_id)
        elif data == "back_main":
            send_main_menu(chat_id)
        elif data == "back_buy":
            send_buy_menu(chat_id, message_id)
        elif data == "buy_go_main":
            send_buy_type_menu(chat_id, "GO", message_id)
        elif data == "buy_plus_main":
            send_buy_type_menu(chat_id, "PLUS", message_id)
        elif data == "buy_team_main":
            send_buy_type_menu(chat_id, "TEAM", message_id)
        elif data == "buy_edu_main":
            send_buy_type_menu(chat_id, "EDU", message_id)
        elif data == "buy_go_shop":
            show_main_package(chat_id, user_id, username, "GO", "shop", message_id)
        elif data == "buy_go_own":
            show_main_package(chat_id, user_id, username, "GO", "own", message_id)
        elif data == "buy_plus_shop":
            show_main_package(chat_id, user_id, username, "PLUS", "shop", message_id)
        elif data == "buy_plus_own":
            show_main_package(chat_id, user_id, username, "PLUS", "own", message_id)
        elif data == "buy_team_shop":
            show_main_package(chat_id, user_id, username, "TEAM", "shop", message_id)
        elif data == "buy_team_own":
            show_main_package(chat_id, user_id, username, "TEAM", "own", message_id)
        elif data == "buy_edu_shop":
            show_main_package(chat_id, user_id, username, "EDU", "shop", message_id)
        elif data == "confirm_paid":
            state = USER_STATE.get(user_id) or {}
            payment_code = state.get("payment_code")
            if not payment_code:
                tg_send_message(chat_id, "Bot không tìm thấy đơn cần xác nhận. Vui lòng dùng /start để chọn lại.")
                return PlainTextResponse("OK")
            orders = load_gist_json(PENDING_ORDERS_FILE)
            if payment_code in orders:
                orders[payment_code]["status"] = "user_confirmed"
                save_gist_json(PENDING_ORDERS_FILE, orders)
            tg_send_message(chat_id, "✅ Đã ghi nhận. Bot sẽ chờ webhook payOS hoặc bạn có thể bấm 'Kiểm tra trạng thái'.")
        elif data == "check_payment_status":
            result = sync_order_status_for_user(user_id)
            tg_send_message(chat_id, result["message"])
        elif data == "free_go":
            send_free_item_from_gist(chat_id, user_id, "GO", message_id)
        elif data == "free_edu":
            send_free_item_from_gist(chat_id, user_id, "EDU", message_id)
        elif data == "free_plus":
            send_free_item_from_gist(chat_id, user_id, "PLUS", message_id)
        elif data == "free_canva_edu":
            send_free_item_from_gist(chat_id, user_id, "CANVA_EDU", message_id)
        elif data.startswith("adm_"):
            if user_id != ADMIN_CHAT_ID:
                tg_send_message(chat_id, "❌ Bạn không phải ADMIN, không thể thao tác đơn.")
                return PlainTextResponse("OK")
            try:
                action, payment_code = data.split("|", 1)
            except ValueError:
                tg_send_message(chat_id, "Dữ liệu nút không hợp lệ.")
                return PlainTextResponse("OK")
            orders = load_gist_json(PENDING_ORDERS_FILE)
            order = orders.get(payment_code)
            if not order:
                tg_send_message(chat_id, f"Không tìm thấy đơn {payment_code}.")
                return PlainTextResponse("OK")
            customer_chat_id = order["chat_id"]
            customer_username = order.get("username") or ""
            if action == "adm_ok":
                process_paid_order(order, payment_code, manual=True)
                tg_send_message(chat_id, f"✅ Đã xác nhận ĐỦ TIỀN cho đơn {payment_code} (user @{customer_username}).")
                return PlainTextResponse("OK")
            if action == "adm_under":
                order["status"] = "underpaid"
                orders[payment_code] = order
                save_gist_json(PENDING_ORDERS_FILE, orders)
                tg_send_message(customer_chat_id, "⚠ Admin xác nhận bạn chuyển thiếu. Vui lòng kiểm tra lại và liên hệ admin.")
                tg_send_message(chat_id, f"⚠ Đã đánh dấu đơn {payment_code} là CHUYỂN THIẾU.")
                return PlainTextResponse("OK")
            if action == "adm_over":
                process_paid_order(order, payment_code, manual=True)
                tg_send_message(customer_chat_id, "ℹ Admin xác nhận bạn chuyển thừa. Gói vẫn được kích hoạt bình thường.")
                tg_send_message(chat_id, f"💸 Đã đánh dấu đơn {payment_code} là CHUYỂN THỪA và xử lý như thanh toán đủ.")
                return PlainTextResponse("OK")
            if action == "adm_none":
                order["status"] = "no_payment"
                orders[payment_code] = order
                save_gist_json(PENDING_ORDERS_FILE, orders)
                tg_send_message(customer_chat_id, "❌ Admin hiện chưa thấy giao dịch tương ứng với đơn của bạn.")
                tg_send_message(chat_id, f"❌ Đã đánh dấu đơn {payment_code} là KHÔNG THẤY TIỀN.")
                return PlainTextResponse("OK")
        return PlainTextResponse("OK")

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

    if text.startswith(("/xacnhan", "/xacnhan_thieu", "/xacnhan_thua", "/xacnhan_khong")):
        handle_admin_confirm(chat_id, user_id, text)
        return PlainTextResponse("OK")

    if text.startswith("/start"):
        save_user_to_gist(user_id)
        send_main_menu(chat_id)
        return PlainTextResponse("OK")

    state = USER_STATE.get(user_id) or {}
    package = state.get("awaiting_info")
    account_type = state.get("account_type")
    payment_code = state.get("payment_code")

    if package and payment_code:
        info = text
        update_pending_order_info(payment_code, info)
        send_admin_message(
            f"KHÁCH GỬI THÔNG TIN\n"
            f"User: @{username} (ID {user_id})\n"
            f"Gói: {package} ({account_type})\n"
            f"Mã thanh toán: {payment_code}\n"
            f"Thông tin:\n{info}"
        )
        tg_send_message(chat_id, "✅ Đã nhận thông tin của bạn. Khi thanh toán thành công, bot sẽ tự xử lý.")
        return PlainTextResponse("OK")

    tg_send_message(chat_id, "ℹ️ Vui lòng dùng /start để mở menu và chọn gói.")
    return PlainTextResponse("OK")


@app.post(PAYOS_WEBHOOK_PATH)
async def payos_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    if PAYOS_CHECKSUM_KEY and payload.get("signature"):
        if not verify_payos_webhook_signature(payload):
            return JSONResponse({"ok": False, "error": "invalid_signature"}, status_code=400)

    data = payload.get("data") or {}
    order_code = data.get("orderCode")
    amount = int(data.get("amount") or 0)
    transaction_ref = data.get("reference") or data.get("paymentLinkId") or ""

    if not order_code:
        return JSONResponse({"ok": False, "error": "missing_order_code"}, status_code=400)

    payment_code, order, orders = find_pending_order_by_order_code(order_code)
    if not payment_code or not order:
        return {"ok": True, "status": "ignored_order_not_found"}

    if order.get("delivery_status") == "delivered":
        return {"ok": True, "status": "duplicate_ignored"}

    expected_amount = PACKAGE_PRICES[order["package"]][order["account_type"]]
    if amount < expected_amount:
        order["status"] = "underpaid"
        order["amount"] = amount
        orders[payment_code] = order
        save_gist_json(PENDING_ORDERS_FILE, orders)
        tg_send_message(order["chat_id"], f"⚠ Thanh toán chưa đủ. Bạn đã chuyển {amount}đ, cần {expected_amount}đ.")
        return {"ok": True, "status": "underpaid"}

    result = process_paid_order(order, payment_code, order_amount=amount, manual=False, transaction_ref=transaction_ref)
    return {"ok": True, **result}


@app.get("/payos-return")
def payos_return(orderCode: int | None = None, status: str | None = None, id: str | None = None):
    return {"ok": True, "message": "Đã quay lại từ payOS", "orderCode": orderCode, "status": status, "id": id}


@app.get("/payos-cancel")
def payos_cancel(orderCode: int | None = None, status: str | None = None, id: str | None = None):
    return {"ok": True, "message": "Khách đã hủy hoặc thoát trang thanh toán", "orderCode": orderCode, "status": status, "id": id}


@app.get("/")
def home():
    return {
        "status": "running",
        "webhook_path": WEBHOOK_PATH,
        "webhook_url": WEBHOOK_URL,
        "payos_webhook_path": PAYOS_WEBHOOK_PATH,
        "payos_webhook_url": PAYOS_WEBHOOK_URL,
        "payos_return_url": PAYOS_RETURN_URL,
        "payos_cancel_url": PAYOS_CANCEL_URL,
    }
