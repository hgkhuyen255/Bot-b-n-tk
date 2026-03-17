import json
import os
import time
import requests
import pyotp
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse

# ============================================================
# ENV
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GIST_ID = os.getenv("GIST_ID", "")
GIST_TOKEN = os.getenv("GIST_TOKEN", "")
BANK_ID = os.getenv("BANK_ID", "970436")
ACCOUNT_NUMBER = os.getenv("ACCOUNT_NUMBER", "0711000283429")
CLOUD_RUN_URL = os.getenv("CLOUD_RUN_SERVICE_URL", "")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_URL = f"{CLOUD_RUN_URL}{WEBHOOK_PATH}" if CLOUD_RUN_URL else WEBHOOK_PATH
TG_BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

_admin_env = os.getenv("ADMIN_CHAT_ID", "")
try:
    ADMIN_CHAT_ID = int(_admin_env) if _admin_env else 5816758036
except ValueError:
    ADMIN_CHAT_ID = 5816758036

GIST_URL = f"https://api.github.com/gists/{GIST_ID}" if GIST_ID else ""
GIST_HEADERS = {
    "Authorization": f"token {GIST_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ============================================================
# FILES IN GIST
# ============================================================
USERS_FILE = "users.json"
SETTINGS_FILE = "settings.json"
SECRETS_FILE = "secrets.json"
INVENTORY_FILE = "inventory.json"
CUSTOMERS_FILE = "customers.json"
ORDERS_FILE = "orders.json"
PENDING_ORDERS_FILE = "pending_orders.json"
REMINDER_LOG_FILE = "reminder_log.json"
FREE_REQUESTS_FILE = "free_requests.json"

# ============================================================
# CATALOG / DEFAULT CONFIG
# ============================================================
CATALOG = {
    "chatgpt_shared_5": {
        "name": "ChatGPT chung 5",
        "platform": "ChatGPT",
        "type": "shared",
        "duration_days": 30,
        "price": 69000,
    },
    "chatgpt_shared_3": {
        "name": "ChatGPT chung 3",
        "platform": "ChatGPT",
        "type": "shared",
        "duration_days": 30,
        "price": 119000,
    },
    "chatgpt_shared_2": {
        "name": "ChatGPT chung 2",
        "platform": "ChatGPT",
        "type": "shared",
        "duration_days": 30,
        "price": 149000,
    },
    "chatgpt_private": {
        "name": "ChatGPT cấp riêng",
        "platform": "ChatGPT",
        "type": "private",
        "duration_days": 30,
        "price": 249000,
    },
    "grok_shared": {
        "name": "Grok chung",
        "platform": "Grok",
        "type": "shared",
        "duration_days": 30,
        "price": 69000,
    },
    "grok_private": {
        "name": "Grok cấp riêng",
        "platform": "Grok",
        "type": "private",
        "duration_days": 30,
        "price": 299000,
    },
    "gemini_shared": {
        "name": "Gemini chung",
        "platform": "Gemini",
        "type": "shared",
        "duration_days": 30,
        "price": 59000,
    },
    "gemini_private": {
        "name": "Gemini cấp riêng",
        "platform": "Gemini",
        "type": "private",
        "duration_days": 30,
        "price": 199000,
    },
    "capcut_shared": {
        "name": "CapCut chung",
        "platform": "CapCut",
        "type": "shared",
        "duration_days": 30,
        "price": 49000,
    },
}

PLATFORM_TREE = {
    "ChatGPT": ["chatgpt_shared_5", "chatgpt_shared_3", "chatgpt_shared_2", "chatgpt_private"],
    "Gemini": ["gemini_shared", "gemini_private"],
    "Grok": ["grok_shared", "grok_private"],
    "CapCut": ["capcut_shared"],
}

TERM_OPTIONS = [1, 3, 6, 12]
TERM_DISCOUNTS = {
    1: 0.00,
    3: 0.05,
    6: 0.10,
    12: 0.18,
}

FREE_GIFTS = {
    "chatgpt_free": {
        "name": "ChatGPT Free",
        "points_cost": 5,
        "kind": "manual",
    },
    "grok_free": {
        "name": "Grok Free",
        "points_cost": 5,
        "kind": "manual",
    },
    "capcut_free": {
        "name": "CapCut Free",
        "points_cost": 3,
        "kind": "manual",
    },
    "canva_edu_free": {
        "name": "Canva Edu miễn phí",
        "points_cost": 0,
        "kind": "email_admin",
        "newbie_gift": True,
    },
}

USER_STATE: Dict[int, Dict[str, Any]] = {}

app = FastAPI()

# ============================================================
# GIST HELPERS
# ============================================================
def _safe_json_load(text: str, fallback: Any) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return fallback


def gist_enabled() -> bool:
    return bool(GIST_URL and GIST_TOKEN)


def default_settings() -> Dict[str, Any]:
    return {
        "shop_name": "Trạm tài khoản số",
        "support": "Liên hệ admin để được hỗ trợ.",
        "bank_id": BANK_ID,
        "account_number": ACCOUNT_NUMBER,
    }


def default_inventory() -> Dict[str, Any]:
    return {code: [] for code in CATALOG}


def load_gist_json(filename: str, fallback: Any) -> Any:
    if not gist_enabled():
        return fallback
    try:
        r = requests.get(GIST_URL, headers=GIST_HEADERS, timeout=20)
        gist = r.json()
        files = gist.get("files", {})
        content = files.get(filename, {}).get("content")
        if content is None:
            return fallback
        return _safe_json_load(content, fallback)
    except Exception as e:
        print(f"GIST READ ERR ({filename}): {e}")
        return fallback


def save_gist_json(filename: str, data: Any) -> None:
    if not gist_enabled():
        return
    try:
        payload = {
            "files": {
                filename: {
                    "content": json.dumps(data, indent=2, ensure_ascii=False)
                }
            }
        }
        requests.patch(GIST_URL, headers=GIST_HEADERS, json=payload, timeout=20)
    except Exception as e:
        print(f"GIST WRITE ERR ({filename}): {e}")


def ensure_bootstrap_files() -> None:
    settings = load_gist_json(SETTINGS_FILE, None)
    if settings is None:
        save_gist_json(SETTINGS_FILE, default_settings())
    inventory = load_gist_json(INVENTORY_FILE, None)
    if inventory is None:
        save_gist_json(INVENTORY_FILE, default_inventory())
    for filename, default in [
        (USERS_FILE, {}),
        (SECRETS_FILE, {}),
        (CUSTOMERS_FILE, {}),
        (ORDERS_FILE, {}),
        (PENDING_ORDERS_FILE, {}),
        (REMINDER_LOG_FILE, {}),
        (FREE_REQUESTS_FILE, {}),
    ]:
        if load_gist_json(filename, None) is None:
            save_gist_json(filename, default)


# ============================================================
# USER / REFERRAL / FREE HELPERS
# ============================================================
def get_users() -> Dict[str, Any]:
    return load_gist_json(USERS_FILE, {})


def save_users(data: Dict[str, Any]):
    save_gist_json(USERS_FILE, data)


def default_user_record(user_id: int, username: str = "", full_name: str = "") -> Dict[str, Any]:
    return {
        "username": username,
        "full_name": full_name,
        "updated_at": now_ts(),
        "joined_at": now_ts(),
        "points": 0,
        "used_points": 0,
        "total_invited": 0,
        "invited_user_ids": [],
        "referral_code": f"ref{user_id}",
        "referred_by": None,
        "canva_newbie_claimed": False,
    }


def ensure_user_record(user_id: int, username: str = "", full_name: str = "") -> Dict[str, Any]:
    users = get_users()
    key = str(user_id)
    record = users.get(key) or default_user_record(user_id, username, full_name)
    record.setdefault("points", 0)
    record.setdefault("used_points", 0)
    record.setdefault("total_invited", 0)
    record.setdefault("invited_user_ids", [])
    record.setdefault("referral_code", f"ref{user_id}")
    record.setdefault("referred_by", None)
    record.setdefault("canva_newbie_claimed", False)
    record["username"] = username or record.get("username", "")
    record["full_name"] = full_name or record.get("full_name", "")
    record["updated_at"] = now_ts()
    record.setdefault("joined_at", now_ts())
    users[key] = record
    save_users(users)
    return record


def update_user_points(user_id: int, delta_points: int = 0, delta_used_points: int = 0) -> Dict[str, Any]:
    users = get_users()
    key = str(user_id)
    record = users.get(key) or default_user_record(user_id)
    record["points"] = max(0, int(record.get("points", 0)) + int(delta_points))
    record["used_points"] = max(0, int(record.get("used_points", 0)) + int(delta_used_points))
    record["updated_at"] = now_ts()
    users[key] = record
    save_users(users)
    return record


def get_user_record(user_id: int) -> Dict[str, Any]:
    users = get_users()
    return users.get(str(user_id)) or default_user_record(user_id)


def find_user_by_referral_code(ref_code: str) -> Optional[int]:
    for uid, info in get_users().items():
        if info.get("referral_code") == ref_code:
            try:
                return int(uid)
            except Exception:
                return None
    return None


def apply_referral_if_needed(user_id: int, username: str, full_name: str, ref_code: str) -> bool:
    users = get_users()
    key = str(user_id)
    record = users.get(key) or default_user_record(user_id, username, full_name)
    if record.get("referred_by"):
        users[key] = record
        save_users(users)
        return False

    inviter_id = find_user_by_referral_code(ref_code)
    if not inviter_id or inviter_id == user_id:
        users[key] = record
        save_users(users)
        return False

    inviter_key = str(inviter_id)
    inviter = users.get(inviter_key) or default_user_record(inviter_id)
    invited_ids = inviter.get("invited_user_ids", [])
    if user_id in invited_ids:
        record["referred_by"] = inviter_id
        users[key] = record
        users[inviter_key] = inviter
        save_users(users)
        return False

    invited_ids.append(user_id)
    inviter["invited_user_ids"] = invited_ids
    inviter["total_invited"] = len(invited_ids)
    inviter["points"] = int(inviter.get("points", 0)) + 1
    inviter["updated_at"] = now_ts()

    record["referred_by"] = inviter_id
    record["updated_at"] = now_ts()

    users[key] = record
    users[inviter_key] = inviter
    save_users(users)

    tg_send_message(inviter_id,
                    "🎉 Bạn vừa mời thành công 1 người mới.\n"
                    f"+1 điểm đã được cộng.\n"
                    f"Điểm hiện có: {inviter['points']}")
    return True


def build_referral_link(user_id: int) -> str:
    user = get_user_record(user_id)
    code = user.get("referral_code", f"ref{user_id}")
    if BOT_USERNAME:
        return f"https://t.me/{BOT_USERNAME}?start={code}"
    return code


def get_free_requests() -> Dict[str, Any]:
    return load_gist_json(FREE_REQUESTS_FILE, {})


def save_free_requests(data: Dict[str, Any]):
    save_gist_json(FREE_REQUESTS_FILE, data)


def make_free_request_code(gift_code: str, user_id: int) -> str:
    return f"free-{gift_code}-{user_id}-{int(time.time())}"


def has_pending_free_request(user_id: int, gift_code: str) -> bool:
    for req in get_free_requests().values():
        if int(req.get("user_id", 0)) == int(user_id) and req.get("gift_code") == gift_code and req.get("status") in {"waiting_email", "pending_admin"}:
            return True
    return False


def create_free_request(user_id: int, username: str, full_name: str, gift_code: str, email: str = "") -> Dict[str, Any]:
    requests_data = get_free_requests()
    req_code = make_free_request_code(gift_code, user_id)
    gift = FREE_GIFTS[gift_code]
    requests_data[req_code] = {
        "request_code": req_code,
        "gift_code": gift_code,
        "gift_name": gift["name"],
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "email": email,
        "points_cost": int(gift.get("points_cost", 0)),
        "status": "pending_admin" if email or gift.get("kind") != "email_admin" else "waiting_email",
        "created_at": now_ts(),
    }
    save_free_requests(requests_data)
    return requests_data[req_code]


def mark_canva_claimed(user_id: int):
    users = get_users()
    key = str(user_id)
    record = users.get(key) or default_user_record(user_id)
    record["canva_newbie_claimed"] = True
    record["updated_at"] = now_ts()
    users[key] = record
    save_users(users)


def refund_points_for_request(req: Dict[str, Any]):
    cost = int(req.get("points_cost", 0) or 0)
    if cost > 0:
        update_user_points(int(req["user_id"]), delta_points=cost, delta_used_points=-cost)


def free_request_admin_keyboard(request_code: str):
    return {
        "inline_keyboard": [
            [{"text": "✅ Add thành công", "callback_data": f"free_ok|{request_code}"}],
            [{"text": "⏳ Tạm hết", "callback_data": f"free_out|{request_code}"}],
        ]
    }


def build_free_admin_text(req: Dict[str, Any]) -> str:
    user_tag = f"@{req.get('username','')}" if req.get("username") else req.get("full_name", "")
    email_line = f"\n- Email: {req.get('email')}" if req.get("email") else ""
    return (
        "🎁 Yêu cầu quà free mới\n"
        f"- Quà: {req.get('gift_name')}\n"
        f"- User: {user_tag} | ID: {req.get('user_id')}\n"
        f"- Điểm trừ: {req.get('points_cost', 0)}{email_line}\n"
        f"- Mã request: {req.get('request_code')}"
    )


def submit_free_request_to_admin(req: Dict[str, Any]):
    send_admin_message(build_free_admin_text(req), reply_markup=free_request_admin_keyboard(req["request_code"]))


def account_summary_text(user_id: int) -> str:
    user = get_user_record(user_id)
    return (
        "👤 Tài khoản của tôi\n\n"
        f"Điểm hiện có: {int(user.get('points', 0))}\n"
        f"Tổng người đã mời: {int(user.get('total_invited', 0))}\n"
        f"Điểm đã dùng đổi quà: {int(user.get('used_points', 0))}\n"
        f"Link / mã mời: {build_referral_link(user_id)}"
    )

# ============================================================
# TELEGRAM HELPERS
# ============================================================
def tg_request(method: str, payload: Dict[str, Any]) -> None:
    try:
        requests.post(f"{TG_BASE_URL}/{method}", json=payload, timeout=20)
    except Exception as e:
        print(f"Telegram {method} error: {e}")


def tg_send_message(chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None, parse_mode: Optional[str] = None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    tg_request("sendMessage", payload)


def tg_send_photo(chat_id: int, photo_url: str, caption: Optional[str] = None, reply_markup: Optional[Dict[str, Any]] = None):
    payload = {"chat_id": chat_id, "photo": photo_url}
    if caption:
        payload["caption"] = caption
    if reply_markup:
        payload["reply_markup"] = reply_markup
    tg_request("sendPhoto", payload)


def tg_edit_message(chat_id: int, message_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    tg_request("editMessageText", payload)


def tg_answer_callback(callback_query_id: str):
    tg_request("answerCallbackQuery", {"callback_query_id": callback_query_id})


def send_admin_message(text: str, reply_markup: Optional[Dict[str, Any]] = None):
    if ADMIN_CHAT_ID:
        tg_send_message(ADMIN_CHAT_ID, text, reply_markup=reply_markup)


# ============================================================
# DATA HELPERS
# ============================================================
def now_ts() -> int:
    return int(time.time())


def save_user(user_id: int, username: str, full_name: str):
    ensure_user_record(user_id, username, full_name)


def get_settings() -> Dict[str, Any]:
    settings = load_gist_json(SETTINGS_FILE, default_settings())
    for k, v in default_settings().items():
        settings.setdefault(k, v)
    return settings


def get_inventory() -> Dict[str, List[Dict[str, Any]]]:
    inventory = load_gist_json(INVENTORY_FILE, default_inventory())
    for code in CATALOG:
        inventory.setdefault(code, [])
    return inventory


def save_inventory(inventory: Dict[str, Any]):
    save_gist_json(INVENTORY_FILE, inventory)


def get_stock_count(product_code: str) -> int:
    inventory = get_inventory()
    return len(inventory.get(product_code, []))


def is_in_stock(product_code: str) -> bool:
    return get_stock_count(product_code) > 0


def stock_label(product_code: str) -> str:
    count = get_stock_count(product_code)
    return f"{count}📦️" if count > 0 else "Hết hàng"


def get_customers() -> Dict[str, Any]:
    return load_gist_json(CUSTOMERS_FILE, {})


def save_customers(data: Dict[str, Any]):
    save_gist_json(CUSTOMERS_FILE, data)


def get_orders() -> Dict[str, Any]:
    return load_gist_json(ORDERS_FILE, {})


def save_orders(data: Dict[str, Any]):
    save_gist_json(ORDERS_FILE, data)


def get_pending_orders() -> Dict[str, Any]:
    return load_gist_json(PENDING_ORDERS_FILE, {})


def save_pending_orders(data: Dict[str, Any]):
    save_gist_json(PENDING_ORDERS_FILE, data)


def get_secrets() -> Dict[str, str]:
    return load_gist_json(SECRETS_FILE, {})


def save_secrets(data: Dict[str, str]):
    save_gist_json(SECRETS_FILE, data)


def get_reminder_log() -> Dict[str, Any]:
    return load_gist_json(REMINDER_LOG_FILE, {})


def save_reminder_log(data: Dict[str, Any]):
    save_gist_json(REMINDER_LOG_FILE, data)


def today_key() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def days_until_expiry(expires_at: int) -> int:
    now = time.time()
    if expires_at <= now:
        return 0
    return int((expires_at - now) // 86400) + 1


def make_payment_code(product_code: str, user_id: int) -> str:
    return f"{product_code}-{user_id}-{int(time.time())}"


def generate_qr(amount: int, payment_code: str) -> str:
    settings = get_settings()
    bank_id = settings.get("bank_id", BANK_ID)
    account_number = settings.get("account_number", ACCOUNT_NUMBER)
    return (
        f"https://img.vietqr.io/image/{bank_id}-{account_number}-compact2.png"
        f"?amount={amount}&addInfo={payment_code}"
    )



def format_money(amount: int) -> str:
    return f"{int(amount):,}đ".replace(",", ".")


def get_term_discount(months: int) -> float:
    return float(TERM_DISCOUNTS.get(months, 0.0))


def get_product_price(product_code: str, months: int = 1) -> int:
    base_price = int(CATALOG[product_code]["price"])
    subtotal = base_price * months
    discount = get_term_discount(months)
    final_price = int(round(subtotal * (1 - discount)))
    return max(final_price, 0)


def get_duration_days_for_months(months: int) -> int:
    return int(months) * 30


def term_label(months: int) -> str:
    return f"{months} tháng"


def customer_active_items(user_id: int) -> List[Dict[str, Any]]:
    customers = get_customers()
    items = customers.get(str(user_id), {}).get("products", [])
    current = now_ts()
    return [x for x in items if int(x.get("expires_at", 0)) > current and x.get("status", "active") == "active"]


def customer_all_items(user_id: int) -> List[Dict[str, Any]]:
    customers = get_customers()
    return customers.get(str(user_id), {}).get("products", [])


def add_customer_product(user_id: int, username: str, full_name: str, product_code: str,
                         account_data: Optional[Dict[str, Any]], duration_days: int,
                         order_code: str, delivered_by: str = "system") -> Dict[str, Any]:
    customers = get_customers()
    key = str(user_id)
    if key not in customers:
        customers[key] = {
            "username": username,
            "full_name": full_name,
            "created_at": now_ts(),
            "products": [],
        }
    expires_at = now_ts() + duration_days * 86400
    record = {
        "product_code": product_code,
        "product_name": CATALOG[product_code]["name"],
        "platform": CATALOG[product_code]["platform"],
        "type": CATALOG[product_code]["type"],
        "duration_days": duration_days,
        "months": max(1, int(duration_days // 30)),
        "expires_at": expires_at,
        "order_code": order_code,
        "status": "active",
        "delivered_by": delivered_by,
        "account": account_data or {},
        "created_at": now_ts(),
    }
    customers[key]["username"] = username
    customers[key]["full_name"] = full_name
    customers[key].setdefault("products", []).append(record)
    save_customers(customers)
    return record


def format_expiry(ts: int) -> str:
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))


def extend_customer_product(user_id: int, item_index: int, duration_days: int,
                            order_code: str, delivered_by: str = "system") -> Dict[str, Any]:
    customers = get_customers()
    key = str(user_id)

    if key not in customers:
        raise ValueError("customer_not_found")

    items = customers[key].get("products", [])
    if item_index < 0 or item_index >= len(items):
        raise ValueError("product_not_found")

    item = items[item_index]
    base_time = max(now_ts(), int(item.get("expires_at", 0) or 0))
    new_expires_at = base_time + duration_days * 86400

    item["expires_at"] = new_expires_at
    item["duration_days"] = int(item.get("duration_days", 0)) + duration_days
    item["months"] = max(1, int(round(item["duration_days"] / 30)))
    item["status"] = "active"
    item["last_renewed_at"] = now_ts()
    item["last_renew_order_code"] = order_code
    item["delivered_by"] = delivered_by

    customers[key]["products"][item_index] = item
    save_customers(customers)
    return item


def allocate_inventory_account(product_code: str) -> Optional[Dict[str, Any]]:
    inventory = get_inventory()
    rows = inventory.get(product_code, [])
    if not rows:
        return None
    acc = rows.pop(0)
    inventory[product_code] = rows
    save_inventory(inventory)
    return acc


def add_inventory_account(product_code: str, username: str, password: str,
                          account_key: str = "", note: str = "") -> None:
    inventory = get_inventory()
    inventory.setdefault(product_code, []).append({
        "username": username,
        "password": password,
        "account_key": account_key,
        "note": note,
        "created_at": now_ts(),
    })
    save_inventory(inventory)


def set_secret(account_key: str, secret: str):
    secrets = get_secrets()
    secrets[account_key] = secret
    save_secrets(secrets)


def delete_secret(account_key: str):
    secrets = get_secrets()
    if account_key in secrets:
        del secrets[account_key]
        save_secrets(secrets)


def get_totp_for_account_key(account_key: str):
    secrets = get_secrets()
    secret = secrets.get(account_key) 
    if not secret:
        return None
    try:
        return pyotp.TOTP(secret).now()
    except Exception:
        return None


def build_expiry_reminder_text(item: Dict[str, Any], days_left: int) -> str:
    product_name = item.get("product_name", "Gói dịch vụ")
    account_username = item.get("account", {}).get("username", "Admin cấp thủ công")
    expiry_text = format_expiry(int(item.get("expires_at", 0)))

    if days_left == 2:
        head = "⏰ Nhắc hạn: gói của bạn còn 2 ngày sẽ hết hạn."
    elif days_left == 1:
        head = "⏰ Nhắc hạn: gói của bạn còn 1 ngày sẽ hết hạn."
    else:
        head = "⚠️ Gói của bạn hết hạn hôm nay."

    return (
        f"{head}\n\n"
        f"Gói: {product_name}\n"
        f"Tài khoản: {account_username}\n"
        f"Hết hạn: {expiry_text}\n\n"
        "Nếu muốn tiếp tục sử dụng, vui lòng gia hạn sớm để tránh gián đoạn và không bị mất quyền lấy mã 2FA."
    )


def build_expiry_reminder_keyboard(item_index: int):
    return {
        "inline_keyboard": [
            [{"text": "🔄 Gia hạn ngay", "callback_data": f"renew|{item_index}"}],
            [{"text": "📦 Tài khoản của tôi", "callback_data": "menu_my"}],
        ]
    }


def process_expiry_reminders() -> Dict[str, Any]:
    customers = get_customers()
    reminder_log = get_reminder_log()
    today = today_key()
    sent = []
    skipped = 0

    for user_id, customer in customers.items():
        items = customer.get("products", [])
        for idx, item in enumerate(items):
            if item.get("status", "active") != "active":
                continue

            expires_at = int(item.get("expires_at", 0) or 0)
            if expires_at <= 0:
                skipped += 1
                continue

            days_left = days_until_expiry(expires_at)
            if days_left not in (2, 1, 0):
                continue

            log_key = f"{user_id}:{idx}:{today}"
            if reminder_log.get(log_key):
                continue

            try:
                tg_send_message(int(user_id), build_expiry_reminder_text(item, days_left), reply_markup=build_expiry_reminder_keyboard(idx))
                reminder_log[log_key] = {
                    "user_id": int(user_id),
                    "product_index": idx,
                    "product_code": item.get("product_code"),
                    "days_left": days_left,
                    "sent_at": now_ts(),
                    "date": today,
                }
                sent.append({
                    "user_id": int(user_id),
                    "product_code": item.get("product_code"),
                    "days_left": days_left,
                })
            except Exception:
                skipped += 1

    save_reminder_log(reminder_log)
    return {
        "ok": True,
        "date": today,
        "sent_count": len(sent),
        "sent": sent,
        "skipped": skipped,
    }


# ============================================================
# UI
# ============================================================
def main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🛒 Mua tài khoản", "callback_data": "menu_buy"}],
            [{"text": "🎁 TK Free", "callback_data": "menu_free"}],
            [{"text": "🔐 Lấy mã 2FA", "callback_data": "menu_2fa"}],
            [{"text": "📦 Tài khoản của tôi", "callback_data": "menu_my"}],
        ]
    }


def free_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "ChatGPT Free · 5 điểm", "callback_data": "free_gift|chatgpt_free"}],
            [{"text": "Grok Free · 5 điểm", "callback_data": "free_gift|grok_free"}],
            [{"text": "Canva Edu miễn phí · quà tân thủ", "callback_data": "free_gift|canva_edu_free"}],
            [{"text": "CapCut Free · 3 điểm", "callback_data": "free_gift|capcut_free"}],
            [{"text": "👥 Mời bạn bè / điểm", "callback_data": "menu_referral"}],
            [{"text": "⬅️ Về menu", "callback_data": "home"}],
        ]
    }


def free_back_keyboard():
    return {"inline_keyboard": [[{"text": "⬅️ Về TK Free", "callback_data": "menu_free"}]]}


def platform_menu_keyboard():
    rows = []
    for platform in ["ChatGPT", "Gemini", "Grok", "CapCut"]:
        rows.append([{"text": f"{platform}", "callback_data": f"platform|{platform}"}])
    rows.append([{"text": "⬅️ Về menu", "callback_data": "home"}])
    return {"inline_keyboard": rows}


def product_menu_keyboard(platform: str):
    rows = []
    for code in PLATFORM_TREE.get(platform, []):
        item = CATALOG[code]
        rows.append([{
            "text": f"{item['name']} - từ {format_money(get_product_price(code, 1))}/tháng | {stock_label(code)}",
            "callback_data": f"buy|{code}",
        }])
    rows.append([{"text": "⬅️ Chọn nền tảng khác", "callback_data": "menu_buy"}])
    return {"inline_keyboard": rows}


def term_menu_keyboard(product_code: str):
    rows = []
    stock = stock_label(product_code)
    for months in TERM_OPTIONS:
        total_price = get_product_price(product_code, months)
        label = f"{term_label(months)} | {format_money(total_price)} | {stock}"
        rows.append([{
            "text": label,
            "callback_data": f"term|{product_code}|{months}",
        }])
    rows.append([{"text": "⬅️ Quay lại sản phẩm", "callback_data": f"platform|{CATALOG[product_code]['platform']}"}])
    return {"inline_keyboard": rows}


def confirm_buy_keyboard(product_code: str, months: int):
    return {
        "inline_keyboard": [
            [{"text": "💳 Thanh toán", "callback_data": f"pay|{product_code}|{months}"}],
            [{"text": "⬅️ Chọn thời hạn khác", "callback_data": f"buy|{product_code}"}],
        ]
    }


def payment_confirm_keyboard(payment_code: str):
    return {
        "inline_keyboard": [
            [{"text": "✅ Tôi đã chuyển khoản", "callback_data": f"paid|{payment_code}"}],
            [{"text": "⬅️ Về menu", "callback_data": "home"}],
        ]
    }


def admin_order_keyboard(order_code: str):
    return {
        "inline_keyboard": [
            [{"text": "✅ Xác nhận đơn", "callback_data": f"adm_ok|{order_code}"}],
            [{"text": "⚠️ Thiếu tiền", "callback_data": f"adm_under|{order_code}"},
             {"text": "❌ Không thấy tiền", "callback_data": f"adm_none|{order_code}"}],
        ]
    }


def active_2fa_keyboard(user_id: int):
    active = customer_active_items(user_id)
    rows = []
    for idx, item in enumerate(active):
        account_key = item.get("account", {}).get("username")
        if account_key:
            label = f"{item['product_name']} | {item.get('account', {}).get('username', 'N/A')}"
            rows.append([{"text": label[:60], "callback_data": f"get2fa|{idx}"}])
    if not rows:
        rows = [[{"text": "Chưa có gói hợp lệ", "callback_data": "noop"}]]
    rows.append([{"text": "⬅️ Về menu", "callback_data": "home"}])
    return {"inline_keyboard": rows}


def my_products_keyboard(user_id: int):
    items = customer_all_items(user_id)
    current = now_ts()
    rows = []

    for idx, item in enumerate(items):
        product_code = item.get("product_code")
        if product_code not in CATALOG:
            continue

        status_active = int(item.get("expires_at", 0)) > current and item.get("status") == "active"
        label_status = "Còn hạn" if status_active else "Hết hạn"
        rows.append([{
            "text": f"🔄 Gia hạn {item.get('product_name', 'Gói')} | {label_status}"[:64],
            "callback_data": f"renew|{idx}",
        }])

    if not rows:
        rows = [[{"text": "⬅️ Về menu", "callback_data": "home"}]]
    else:
        rows.append([{"text": "⬅️ Về menu", "callback_data": "home"}])
    return {"inline_keyboard": rows}


def renew_term_menu_keyboard(user_id: int, item_index: int):
    items = customer_all_items(user_id)
    if item_index < 0 or item_index >= len(items):
        return {"inline_keyboard": [[{"text": "⬅️ Về menu", "callback_data": "home"}]]}

    item = items[item_index]
    product_code = item["product_code"]
    rows = []

    for months in TERM_OPTIONS:
        total_price = get_product_price(product_code, months)
        rows.append([{
            "text": f"{term_label(months)} | {format_money(total_price)}",
            "callback_data": f"renew_term|{item_index}|{months}",
        }])

    rows.append([{"text": "⬅️ Quay lại tài khoản của tôi", "callback_data": "menu_my"}])
    return {"inline_keyboard": rows}


def renew_confirm_keyboard(item_index: int, months: int):
    return {
        "inline_keyboard": [
            [{"text": "💳 Thanh toán gia hạn", "callback_data": f"renew_pay|{item_index}|{months}"}],
            [{"text": "⬅️ Chọn thời hạn khác", "callback_data": f"renew|{item_index}"}],
        ]
    }


# ============================================================
# MESSAGES
# ============================================================
def home_text() -> str:
    settings = get_settings()
    return (
        f"🎉 Chào mừng đến với {settings.get('shop_name', 'Trạm tài khoản số')}\n\n"
        "Bot hoạt động 24h:\n"
        "Cung cấp tài khoản số uy tín:\n"
        "- Mua tài khoản dùng chung / cấp riêng\n"
        "⚡ Tự động cấp – quản lý – gia hạn\n"
        "🔐 Lấy mã 2FA nhanh chóng dễ dàng\n\n"
        "📞 Hỗ trợ:\n"
        "Telegram: @tkminer\n"
        "Zalo: 0326805803\n\n"
        "👉 Chọn chức năng bên dưới để bắt đầu."
    )


def product_detail_text(product_code: str, months: int = 1) -> str:
    item = CATALOG[product_code]
    type_vi = "Tài khoản dùng chung" if item["type"] == "shared" else "Tài khoản cấp riêng"
    total_price = get_product_price(product_code, months)
    duration_days = get_duration_days_for_months(months)
    return (
        f"📦 {item['name']}\n\n"
        f"Nền tảng: {item['platform']}\n"
        f"Loại: {type_vi}\n"
        f"Thời hạn đang chọn: {term_label(months)} ({duration_days} ngày)\n"
        f"Giá thanh toán: {format_money(total_price)}\n"
        f"Kho hiện tại: {stock_label(product_code)}\n\n"
        "Sau khi thanh toán và được xác nhận, bot sẽ cấp tài khoản hoặc ghi nhận để admin cấp riêng.\n"
        "Mã 2FA chỉ lấy được khi gói còn hạn."
    )


def my_products_text(user_id: int) -> str:
    items = customer_all_items(user_id)
    if not items:
        return "📦 Bạn chưa có gói nào được kích hoạt."
    current = now_ts()
    lines = ["📦 Danh sách gói của bạn:\n"]
    for idx, item in enumerate(items, 1):
        status = "Còn hạn" if int(item.get("expires_at", 0)) > current and item.get("status") == "active" else "Hết hạn"
        acc = item.get("account", {})
        account_line = acc.get("username", "Admin cấp thủ công")
        months = int(item.get("months", max(1, int(item.get("duration_days", 30) // 30))))
        lines.append(
            f"{idx}. {item['product_name']}\n"
            f"- Thời hạn: {term_label(months)}\n"
            f"- TK: {account_line}\n"
            f"- Hết hạn: {format_expiry(int(item.get('expires_at', 0)))}\n"
            f"- Trạng thái: {status}\n"
        )
    return "\n".join(lines)


def free_menu_text(user_id: int) -> str:
    user = get_user_record(user_id)
    return (
        "🎁 TK Free\n\n"
        "Quà hiện có:\n"
        "- ChatGPT Free: đổi 5 điểm\n"
        "- Grok Free: đổi 5 điểm\n"
        "- CapCut Free: đổi 3 điểm\n"
        "- Canva Edu miễn phí: quà tân thủ, không trừ điểm\n\n"
        "Mỗi user mới mời thành công = +1 điểm.\n"
        "Khi đổi quà bằng điểm, hệ thống sẽ trừ điểm ngay khi gửi yêu cầu.\n\n"
        f"Điểm hiện có: {int(user.get('points', 0))}"
    )


def referral_menu_text(user_id: int) -> str:
    return (
        "👥 Hệ thống mời bạn bè / điểm\n\n"
        "- Mỗi user mới mời thành công = +1 điểm\n"
        "- ChatGPT Free / Grok Free: 5 điểm\n"
        "- CapCut Free: 3 điểm\n"
        "- Canva Edu Free: quà tân thủ, không trừ điểm\n\n"
        f"{account_summary_text(user_id)}"
    )


def free_gift_detail_text(user_id: int, gift_code: str) -> str:
    gift = FREE_GIFTS[gift_code]
    user = get_user_record(user_id)
    cost = int(gift.get("points_cost", 0))
    extra = "Quà tân thủ, không trừ điểm." if gift_code == "canva_edu_free" else f"Điểm cần đổi: {cost}."
    note = "Bấm nhận rồi nhập email để admin add Canva Edu." if gift_code == "canva_edu_free" else "Bấm nhận để gửi yêu cầu xử lý quà free cho admin."
    return (
        f"🎁 {gift['name']}\n\n"
        f"{extra}\n"
        f"Điểm hiện có: {int(user.get('points', 0))}\n\n"
        f"{note}"
    )


def free_gift_confirm_keyboard(gift_code: str):
    return {
        "inline_keyboard": [
            [{"text": "🎁 Nhận quà", "callback_data": f"free_claim|{gift_code}"}],
            [{"text": "⬅️ Về TK Free", "callback_data": "menu_free"}],
        ]
    }

# ============================================================
# ORDER PROCESSING
# ============================================================
def create_pending_order(user_id: int, chat_id: int, username: str, full_name: str, product_code: str, months: int = 1) -> Dict[str, Any]:
    orders = get_pending_orders()
    order_code = make_payment_code(product_code, user_id)
    price = get_product_price(product_code, months)
    duration_days = get_duration_days_for_months(months)
    orders[order_code] = {
        "order_code": order_code,
        "user_id": user_id,
        "chat_id": chat_id,
        "username": username,
        "full_name": full_name,
        "product_code": product_code,
        "months": months,
        "price": price,
        "base_monthly_price": int(CATALOG[product_code]["price"]),
        "discount_percent": int(get_term_discount(months) * 100),
        "duration_days": duration_days,
        "status": "waiting_payment",
        "created_at": now_ts(),
    }
    save_pending_orders(orders)
    return orders[order_code]


def finalize_order(order_code: str, delivered_by: str = "system") -> Dict[str, Any]:
    pending = get_pending_orders()
    order = pending.get(order_code)
    if not order:
        raise ValueError("order_not_found")

    product_code = order["product_code"]
    item = CATALOG[product_code]
    account_data = None
    message = ""

    if item["type"] == "shared":
        account_data = allocate_inventory_account(product_code)
        if account_data:
            message = (
                "✅ Thanh toán đã được xác nhận.\n\n"
                f"Tài khoản: {account_data.get('username', '')}\n"
                f"Mật khẩu: {account_data.get('password', '')}\n"
            )
            if account_data.get("note"):
                message += f"Ghi chú: {account_data['note']}\n"
            if account_data.get("username"):
                message += "\nBạn có thể vào mục 🔐 Lấy mã 2FA khi cần."
        else:
            message = (
                "✅ Thanh toán đã được xác nhận.\n"
                "Hiện kho tài khoản dùng chung đang tạm hết, admin sẽ cấp thủ công sớm nhất."
            )
    else:
        message = (
            "✅ Thanh toán đã được xác nhận.\n"
            "Admin sẽ cấp tài khoản riêng cho bạn. Sau khi cấp xong, bot vẫn quản lý hạn dùng và 2FA bình thường."
        )

    add_customer_product(
        user_id=order["user_id"],
        username=order.get("username", ""),
        full_name=order.get("full_name", ""),
        product_code=product_code,
        account_data=account_data,
        duration_days=int(order["duration_days"]),
        order_code=order_code,
        delivered_by=delivered_by,
    )

    all_orders = get_orders()
    all_orders[order_code] = {
        **order,
        "status": "paid",
        "paid_at": now_ts(),
        "delivered_by": delivered_by,
        "account_data": account_data,
    }
    save_orders(all_orders)

    del pending[order_code]
    save_pending_orders(pending)

    tg_send_message(order["chat_id"], message)
    return all_orders[order_code]


# ============================================================
# ADMIN COMMANDS
# ============================================================
def is_admin(user_id: int) -> bool:
    return bool(ADMIN_CHAT_ID and user_id == ADMIN_CHAT_ID)


def admin_help() -> str:
    return (
        "🛠 Lệnh admin:\n\n"
        "/addstock <product_code> <username> <password> [note]\n"
        "/addsecret <username> <base32_secret>\n"
        "/delsecret <username>\n"
        "/grant <user_id> <product_code> <days> <username> <password>\n"
        "/setprice <product_code> <price>\n"
        "/orders\n"
        "/inventory\n"
        "/products\n"
        "/checkstock [product_code]\n"
        "/free_requests\n"
        "/remindnow\n"
        "/broadcast <message>"
    )


def handle_admin_command(chat_id: int, user_id: int, text: str):
    if not is_admin(user_id):
        tg_send_message(chat_id, "❌ Bạn không phải admin.")
        return

    parts = text.split()
    cmd = parts[0].lower()

    if cmd == "/admin":
        tg_send_message(chat_id, admin_help())
        return

    if cmd == "/products":
        lines = ["📋 Product code hiện có:"]
        for code, item in CATALOG.items():
            lines.append(f"- {code}: {item['name']} | từ {format_money(item['price'])}/tháng | {stock_label(code)}")
        tg_send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/checkstock":
        if len(parts) >= 2:
            code = parts[1]
            if code not in CATALOG:
                tg_send_message(chat_id, "❌ product_code không tồn tại.")
                return
            tg_send_message(chat_id, f"📦 {code} | {CATALOG[code]['name']} | Còn {get_stock_count(code)} tài khoản")
            return
        lines = ["📦 Kiểm tra kho hiện tại:"]
        for code, item in CATALOG.items():
            lines.append(f"- {code}: {item['name']} | {stock_label(code)}")
        tg_send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/remindnow":
        result = process_expiry_reminders()
        tg_send_message(
            chat_id,
            f"✅ Đã chạy nhắc hạn. Ngày: {result['date']} | Đã gửi: {result['sent_count']} | Bỏ qua: {result['skipped']}"
        )
        return

    if cmd == "/inventory":
        inventory = get_inventory()
        lines = ["📦 Tồn kho:"]
        for code, rows in inventory.items():
            lines.append(f"- {code}: {len(rows)} tài khoản | {stock_label(code)}")
        tg_send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/orders":
        pending = get_pending_orders()
        if not pending:
            tg_send_message(chat_id, "Không có đơn chờ.")
            return
        lines = ["🧾 Đơn đang chờ:"]
        for k, v in pending.items():
            lines.append(f"- {k} | {v['product_code']} | {term_label(int(v.get('months', 1)))} | {v.get('username','')} | {format_money(v['price'])}")
        tg_send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/free_requests":
        data = get_free_requests()
        rows = [r for r in data.values() if r.get("status") in {"waiting_email", "pending_admin"}]
        if not rows:
            tg_send_message(chat_id, "Không có yêu cầu quà free đang chờ.")
            return
        lines = ["🎁 Yêu cầu free đang chờ:"]
        for r in rows[-20:]:
            lines.append(f"- {r['request_code']} | {r['gift_name']} | {r.get('username','')} | {r.get('email','không có email')} | {r['status']}")
        tg_send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/addsecret" and len(parts) >= 3:
        account_key, secret = parts[1], parts[2]
        set_secret(account_key, secret)
        tg_send_message(chat_id, f"✅ Đã lưu secret cho {account_key}.")
        return

    if cmd == "/delsecret" and len(parts) >= 2:
        account_key = parts[1]
        delete_secret(account_key)
        tg_send_message(chat_id, f"✅ Đã xoá secret của {account_key}.")
        return

    if cmd == "/setprice" and len(parts) >= 3:
        code = parts[1]
        if code not in CATALOG:
            tg_send_message(chat_id, "❌ product_code không tồn tại.")
            return
        try:
            price = int(parts[2])
        except ValueError:
            tg_send_message(chat_id, "❌ Giá không hợp lệ.")
            return
        CATALOG[code]["price"] = price
        tg_send_message(chat_id, f"✅ Đã cập nhật giá {code} = {price:,}đ".replace(",", "."))
        return

    if cmd == "/addstock" and len(parts) >= 4:
        product_code = parts[1]
        if product_code not in CATALOG:
            tg_send_message(chat_id, "❌ product_code không tồn tại.")
            return
        username = parts[2]
        password = parts[3]
        account_key = parts[4] if len(parts) >= 5 else ""
        note = " ".join(parts[5:]) if len(parts) >= 6 else ""
        add_inventory_account(product_code, username, password, account_key, note)
        tg_send_message(chat_id, f"✅ Đã thêm kho cho {product_code}. Tồn kho hiện tại: {get_stock_count(product_code)}")
        return
    if cmd == "/broadcast":
        if len(parts) < 2:
            tg_send_message(chat_id, "❌ Nhập nội dung cần gửi.")
            return
    
        message_text = text.replace("/broadcast", "", 1).strip()
        users = get_users()
    
        success = 0
        fail = 0
    
        for uid in users.keys():
            try:
                tg_send_message(int(uid), message_text)
                success += 1
                time.sleep(0.05)  # tránh spam limit
            except:
                fail += 1
    
        tg_send_message(chat_id,
            f"📢 Broadcast xong\n"
            f"✅ Thành công: {success}\n"
            f"❌ Lỗi: {fail}"
        )
        return
    if cmd == "/grant" and len(parts) >= 6:
        try:
            target_user_id = int(parts[1])
            product_code = parts[2]
            days = int(parts[3])
        except ValueError:
            tg_send_message(chat_id, "❌ Sai định dạng /grant.")
            return
    
        if product_code not in CATALOG:
            tg_send_message(chat_id, "❌ product_code không tồn tại.")
            return
    
        username_acc = parts[4]
        password_acc = parts[5]
    
        users = load_gist_json(USERS_FILE, {})
        user_info = users.get(str(target_user_id), {})
    
        record = add_customer_product(
            user_id=target_user_id,
            username=user_info.get("username", ""),
            full_name=user_info.get("full_name", ""),
            product_code=product_code,
            account_data={
                "username": username_acc,
                "password": password_acc,
            },
            duration_days=days,
            order_code=f"manual-{int(time.time())}",
            delivered_by="admin",
        )
    
        tg_send_message(
            chat_id,
            f"✅ Đã cấp thủ công cho user {target_user_id}. Hết hạn: {format_expiry(record['expires_at'])}"
        )
    
        tg_send_message(
            target_user_id,
            f"🎁 Admin đã cấp cho bạn: {CATALOG[product_code]['name']}\n"
            f"Tài khoản: {username_acc}\n"
            f"Mật khẩu: {password_acc}\n"
            f"Hết hạn: {format_expiry(record['expires_at'])}"
        )
        return
    
    tg_send_message(chat_id, "❌ Lệnh không hợp lệ. Dùng /admin để xem hướng dẫn.")


# ============================================================
# CALLBACKS / MESSAGES
# ============================================================
def open_home(chat_id: int, message_id: Optional[int] = None):
    text = home_text()
    if message_id:
        tg_edit_message(chat_id, message_id, text, reply_markup=main_menu_keyboard())
    else:
        tg_send_message(chat_id, text, reply_markup=main_menu_keyboard())


def handle_callback(cq: Dict[str, Any]):
    data = cq.get("data", "")
    message = cq.get("message", {}) or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    user = cq.get("from", {}) or {}
    user_id = user.get("id")
    username = user.get("username", "")
    full_name = " ".join(filter(None, [user.get("first_name", ""), user.get("last_name", "")])).strip()

    if cq.get("id"):
        tg_answer_callback(cq["id"])

    if not chat_id or not user_id:
        return

    save_user(user_id, username, full_name)

    if data == "noop":
        return
    if data == "home":
        open_home(chat_id, message_id)
        return
    if data == "menu_buy":
        tg_edit_message(chat_id, message_id, "🛒 Chọn nền tảng cần mua:", reply_markup=platform_menu_keyboard())
        return
    if data == "menu_free":
        tg_edit_message(chat_id, message_id, free_menu_text(user_id), reply_markup=free_menu_keyboard())
        return
    if data == "menu_referral":
        tg_edit_message(chat_id, message_id, referral_menu_text(user_id), reply_markup=free_back_keyboard())
        return
    if data == "menu_support":
        tg_edit_message(chat_id, message_id, get_settings().get("support", "Liên hệ admin để được hỗ trợ."), reply_markup=main_menu_keyboard())
        return
    if data == "menu_my":
        tg_edit_message(chat_id, message_id, my_products_text(user_id), reply_markup=my_products_keyboard(user_id))
        return
    if data.startswith("free_gift|"):
        gift_code = data.split("|", 1)[1]
        if gift_code not in FREE_GIFTS:
            tg_send_message(chat_id, "❌ Quà không hợp lệ.")
            return
        tg_edit_message(chat_id, message_id, free_gift_detail_text(user_id, gift_code), reply_markup=free_gift_confirm_keyboard(gift_code))
        return
    if data.startswith("free_claim|"):
        gift_code = data.split("|", 1)[1]
        if gift_code not in FREE_GIFTS:
            tg_send_message(chat_id, "❌ Quà không hợp lệ.")
            return
        user_info = get_user_record(user_id)
        if has_pending_free_request(user_id, gift_code):
            tg_send_message(chat_id, "⚠️ Bạn đang có yêu cầu quà này chờ xử lý rồi.")
            return
        if gift_code == "canva_edu_free":
            if bool(user_info.get("canva_newbie_claimed", False)):
                tg_send_message(chat_id, "⚠️ Bạn đã nhận quà tân thủ Canva Edu trước đó rồi.")
                return
            USER_STATE[user_id] = {"awaiting_canva_email": True, "gift_code": gift_code}
            tg_send_message(chat_id, "📩 Vui lòng nhập email để admin add Canva Edu miễn phí.")
            return
        cost = int(FREE_GIFTS[gift_code].get("points_cost", 0))
        if int(user_info.get("points", 0)) < cost:
            tg_send_message(chat_id, f"⚠️ Bạn chưa đủ điểm để đổi quà này. Cần {cost} điểm.")
            return
        update_user_points(user_id, delta_points=-cost, delta_used_points=cost)
        req = create_free_request(user_id, username, full_name, gift_code)
        submit_free_request_to_admin(req)
        tg_send_message(chat_id,
                        f"✅ Đã gửi yêu cầu nhận {FREE_GIFTS[gift_code]['name']}.\n"
                        f"Hệ thống đã trừ {cost} điểm. Admin sẽ xử lý sớm.")
        return
    if data == "menu_2fa":
        tg_edit_message(chat_id, message_id,
                        "🔐 Chọn tài khoản còn hạn để lấy mã 2FA.\nKhách hết hạn sẽ không lấy được mã.",
                        reply_markup=active_2fa_keyboard(user_id))
        return
    if data.startswith("platform|"):
        platform = data.split("|", 1)[1]
        tg_edit_message(chat_id, message_id, f"🛒 {platform} - chọn gói:", reply_markup=product_menu_keyboard(platform))
        return
    if data.startswith("buy|"):
        code = data.split("|", 1)[1]
        tg_edit_message(chat_id, message_id, product_detail_text(code), reply_markup=term_menu_keyboard(code))
        return
    if data.startswith("term|"):
        _, code, months_raw = data.split("|", 2)
        months = int(months_raw)
        tg_edit_message(chat_id, message_id, product_detail_text(code, months), reply_markup=confirm_buy_keyboard(code, months))
        return
    if data.startswith("pay|"):
        _, code, months_raw = data.split("|", 2)
        months = int(months_raw)
        if CATALOG[code]["type"] == "shared" and not is_in_stock(code):
            tg_send_message(chat_id, "⚠️ Sản phẩm này hiện đã hết kho, vui lòng chọn gói khác hoặc liên hệ admin.")
            return
        order = create_pending_order(user_id, chat_id, username, full_name, code, months)
        qr_url = generate_qr(order["price"], order["order_code"])
        caption = (
            f"🧾 Mã đơn: {order['order_code']}\n"
            f"Gói: {CATALOG[code]['name']}\n"
            f"Thời hạn: {term_label(months)} ({order['duration_days']} ngày)\n"
            f"Số tiền: {format_money(order['price'])}\n\n"
            "1. Quét QR để thanh toán\n"
            "2. Chuyển đúng nội dung\n"
            "3. Bấm 'Tôi đã chuyển khoản'\n"
            "4. Chờ admin xác nhận"
        )
        tg_send_photo(chat_id, qr_url, caption=caption, reply_markup=payment_confirm_keyboard(order["order_code"]))
        USER_STATE[user_id] = {"latest_order_code": order["order_code"]}
        return
    if data.startswith("paid|"):
        order_code = data.split("|", 1)[1]
        pending = get_pending_orders()
        order = pending.get(order_code)
        if not order:
            tg_send_message(chat_id, "❌ Không tìm thấy đơn chờ thanh toán.")
            return
        order["status"] = "user_confirmed"
        pending[order_code] = order
        save_pending_orders(pending)
        send_admin_message(
            "💸 Khách báo đã chuyển khoản\n"
            f"- User: @{order.get('username', '')} | ID: {order['user_id']}\n"
            f"- Gói: {CATALOG[order['product_code']]['name']}\n"
            f"- Thời hạn: {term_label(int(order.get('months', 1)))}\n"
            f"- Mã đơn: {order_code}\n"
            f"- Số tiền: {format_money(order['price'])}",
            reply_markup=admin_order_keyboard(order_code),
        )
        tg_send_message(chat_id, "✅ Đã ghi nhận. Admin sẽ kiểm tra và xác nhận đơn cho bạn.")
        return
    if data.startswith("get2fa|"):
        try:
            idx = int(data.split("|", 1)[1])
        except ValueError:
            tg_send_message(chat_id, "❌ Dữ liệu không hợp lệ.")
            return
        items = customer_active_items(user_id)
        if idx < 0 or idx >= len(items):
            tg_send_message(chat_id, "❌ Không tìm thấy tài khoản hợp lệ.")
            return
        account_key = items[idx].get("account", {}).get("username")
        if not account_key:
            tg_send_message(chat_id, "⚠️ Tài khoản này chưa được cấu hình 2FA.")
            return
        code = get_totp_for_account_key(account_key)
        if not code:
            tg_send_message(chat_id, "⚠️ Không lấy được mã 2FA. Kiểm tra cấu hình secret.")
            return
        tg_send_message(chat_id,
                        f"🔐 Mã 2FA: {code}\n"
                        f"Tài khoản: {items[idx].get('account', {}).get('username', '')}\n"
                        f"Hết hạn: {format_expiry(int(items[idx]['expires_at']))}")
        return
    if data.startswith("free_ok|") or data.startswith("free_out|"):
        if not is_admin(user_id):
            tg_send_message(chat_id, "❌ Bạn không phải admin.")
            return
        action, request_code = data.split("|", 1)
        requests_data = get_free_requests()
        req = requests_data.get(request_code)
        if not req:
            tg_send_message(chat_id, "❌ Không tìm thấy request free.")
            return
        if req.get("status") not in {"pending_admin", "waiting_email"}:
            tg_send_message(chat_id, "ℹ️ Request này đã xử lý trước đó.")
            return
        if action == "free_ok":
            req["status"] = "done"
            req["processed_at"] = now_ts()
            requests_data[request_code] = req
            save_free_requests(requests_data)
            if req.get("gift_code") == "canva_edu_free":
                mark_canva_claimed(int(req["user_id"]))
                tg_send_message(int(req["user_id"]),
                                "✅ Đã add Canva Edu thành công.\n"
                                "Vui lòng kiểm tra lại email / đăng nhập lại Canva sau ít phút.")
            else:
                tg_send_message(int(req["user_id"]),
                                f"✅ Yêu cầu {req.get('gift_name')} của bạn đã được xử lý thành công.")
            tg_send_message(chat_id, f"✅ Đã xử lý thành công request {request_code}.")
            return
        if action == "free_out":
            req["status"] = "out_of_stock"
            req["processed_at"] = now_ts()
            requests_data[request_code] = req
            save_free_requests(requests_data)
            refund_points_for_request(req)
            if req.get("gift_code") == "canva_edu_free":
                tg_send_message(int(req["user_id"]),
                                "⏳ Hiện Canva Edu free đang tạm hết suất xử lý.\n"
                                "Khi có đợt add tiếp theo bạn có thể gửi lại yêu cầu.")
            else:
                tg_send_message(int(req["user_id"]),
                                f"⏳ {req.get('gift_name')} hiện đang tạm hết suất xử lý.\n"
                                "Khi có đợt tiếp theo bạn có thể gửi lại yêu cầu. Điểm đã được hoàn lại vào tài khoản của bạn.")
            tg_send_message(chat_id, f"⏳ Đã đánh dấu tạm hết cho request {request_code}.")
            return

    if data.startswith("adm_"):
        if not is_admin(user_id):
            tg_send_message(chat_id, "❌ Bạn không phải admin.")
            return
        action, order_code = data.split("|", 1)
        pending = get_pending_orders()
        order = pending.get(order_code)
        if not order:
            tg_send_message(chat_id, "❌ Không tìm thấy đơn.")
            return
        if action == "adm_ok":
            finalized = finalize_order(order_code, delivered_by="admin")
            tg_send_message(chat_id, f"✅ Đã xác nhận đơn {order_code} cho {finalized.get('username', '')}.")
            return
        if action == "adm_under":
            order["status"] = "underpaid"
            pending[order_code] = order
            save_pending_orders(pending)
            tg_send_message(order["chat_id"], "⚠️ Admin xác nhận đơn của bạn đang thiếu tiền. Vui lòng liên hệ để được hỗ trợ.")
            tg_send_message(chat_id, f"⚠️ Đã đánh dấu thiếu tiền: {order_code}")
            return
        if action == "adm_none":
            order["status"] = "no_payment"
            pending[order_code] = order
            save_pending_orders(pending)
            tg_send_message(order["chat_id"], "❌ Admin hiện chưa thấy giao dịch của bạn. Nếu đã chuyển, hãy gửi bill cho admin.")
            tg_send_message(chat_id, f"❌ Đã đánh dấu không thấy tiền: {order_code}")
            return


def handle_text_message(message: Dict[str, Any]):
    chat_id = message.get("chat", {}).get("id")
    user = message.get("from", {}) or {}
    user_id = user.get("id")
    username = user.get("username", "")
    full_name = " ".join(filter(None, [user.get("first_name", ""), user.get("last_name", "")])).strip()
    text = (message.get("text") or "").strip()

    if not chat_id or not user_id:
        return

    save_user(user_id, username, full_name)
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            ref_code = parts[1].strip()
            if ref_code:
                apply_referral_if_needed(user_id, username, full_name, ref_code)
    
        open_home(chat_id)
        return
    if text.startswith((
        "/admin", "/addstock", "/addsecret", "/delsecret", "/grant",
        "/setprice", "/inventory", "/orders", "/products",
        "/checkstock", "/remindnow", "/free_requests", "/broadcast"
    )):
        handle_admin_command(chat_id, user_id, text)
        return
        
        
    if text.startswith("/my"):
        tg_send_message(chat_id, my_products_text(user_id), reply_markup=my_products_keyboard(user_id))
        return
    if text.startswith("/2fa"):
        tg_send_message(chat_id, "🔐 Chọn trong menu để lấy mã 2FA.", reply_markup=active_2fa_keyboard(user_id))
        return

    state = USER_STATE.get(user_id, {})
    if state.get("awaiting_canva_email") and state.get("gift_code") == "canva_edu_free":
        email = text.strip()
        if "@" not in email or "." not in email.split("@")[-1]:
            tg_send_message(chat_id, "❌ Email chưa hợp lệ. Vui lòng nhập lại email Canva của bạn.")
            return
        req = create_free_request(user_id, username, full_name, "canva_edu_free", email=email)
        submit_free_request_to_admin(req)
        USER_STATE.pop(user_id, None)
        tg_send_message(chat_id,
                        "✅ Đã ghi nhận email Canva của bạn và gửi admin xử lý.\n"
                        "Khi có kết quả bot sẽ nhắn lại cho bạn.")
        return

    # Hỗ trợ kiểu cũ: nhập trực tiếp account_key để lấy 2FA, nhưng vẫn kiểm tra còn hạn
    active = customer_active_items(user_id)
    direct = next((x for x in active if x.get("account", {}).get("username") == text), None)
    if direct:
        code = get_totp_for_account_key(text)
        if code:
            tg_send_message(chat_id, f"🔐 Mã 2FA: {code}")
        else:
            tg_send_message(chat_id, "⚠️ Không tìm thấy secret hoặc secret lỗi.")
        return

    tg_send_message(chat_id, "ℹ️ Dùng /start để mở menu bot.")


# ============================================================
# API ROUTES
# ============================================================
@app.on_event("startup")
def on_startup():
    ensure_bootstrap_files()


@app.get("/")
def home():
    return {
        "status": "running",
        "webhook_path": WEBHOOK_PATH,
        "webhook_url": WEBHOOK_URL,
        "catalog_size": len(CATALOG),
        "reminder_endpoint": "/cron/remind_expiring",
    }


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
    except Exception:
        return PlainTextResponse("OK")

    if "callback_query" in update:
        handle_callback(update["callback_query"])
        return PlainTextResponse("OK")

    if "message" in update:
        handle_text_message(update["message"])
        return PlainTextResponse("OK")

    return PlainTextResponse("OK")


@app.post("/cron/remind_expiring")
async def cron_remind_expiring():
    result = process_expiry_reminders()
    return JSONResponse(result)


@app.post("/payment_webhook")
async def payment_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    order_code = payload.get("code")
    amount = payload.get("amount")
    if not order_code:
        return JSONResponse({"ok": False, "error": "missing_code"}, status_code=400)

    pending = get_pending_orders()
    order = pending.get(order_code)
    if not order:
        return JSONResponse({"ok": False, "error": "order_not_found"}, status_code=404)

    expected = int(order["price"])
    if amount is None:
        return JSONResponse({"ok": False, "error": "missing_amount", "expected": expected}, status_code=400)

    try:
        amount = int(amount)
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_amount"}, status_code=400)

    if amount < expected:
        order["status"] = "underpaid"
        pending[order_code] = order
        save_pending_orders(pending)
        tg_send_message(order["chat_id"], f"⚠️ Bạn đã chuyển {amount:,}đ, chưa đủ {expected:,}đ.".replace(",", "."))
        send_admin_message(f"⚠️ Đơn {order_code} chuyển thiếu. Đã nhận {amount:,}đ / cần {expected:,}đ".replace(",", "."))
        return {"ok": True, "status": "underpaid"}

    finalize_order(order_code, delivered_by="payment_webhook")
    if amount > expected:
        tg_send_message(order["chat_id"], f"ℹ️ Hệ thống ghi nhận bạn chuyển thừa {amount - expected:,}đ.".replace(",", "."))
    send_admin_message(f"✅ Đơn {order_code} đã auto xác nhận qua payment webhook.")
    return {"ok": True, "status": "paid"}
