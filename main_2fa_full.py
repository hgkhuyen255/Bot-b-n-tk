import json
import os
import time
import requests
import pyotp
import re
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse

# ============================================================
# ENV
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
GIST_ID = os.getenv("GIST_ID", "")
GIST_TOKEN = os.getenv("GIST_TOKEN", "")
BANK_ID = os.getenv("BANK_ID", "970436")
ACCOUNT_NUMBER = os.getenv("ACCOUNT_NUMBER", "0711000283429")
CLOUD_RUN_URL = os.getenv("CLOUD_RUN_SERVICE_URL", "")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_URL = f"{CLOUD_RUN_URL}{WEBHOOK_PATH}" if CLOUD_RUN_URL else WEBHOOK_PATH
TG_BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

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
REFERRALS_FILE = "referrals.json"
FREE_CLAIMS_FILE = "free_claims.json"
CANVA_REQUESTS_FILE = "canva_requests.json"

# ============================================================
# CATALOG / DEFAULT CONFIG
# ============================================================
CATALOG = {
    "chatgpt_shared_5": {
        "name": "ChatGPT chung 5",
        "platform": "ChatGPT",
        "type": "shared",
        "duration_days": 30,
        "price": 59000,
    },
    "chatgpt_shared_3": {
        "name": "ChatGPT chung 3",
        "platform": "ChatGPT",
        "type": "shared",
        "duration_days": 30,
        "price": 89000,
    },
    "chatgpt_shared_2": {
        "name": "ChatGPT chung 2",
        "platform": "ChatGPT",
        "type": "shared",
        "duration_days": 30,
        "price": 129000,
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
        "price": 199000,
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

FREE_CATALOG = {
    "canva_free": {
        "name": "Canva Edu miễn phí",
        "platform": "TK Free",
        "type": "free",
        "duration_days": 30,
        "reward_type": "join_bonus",
        "required_referrals": 0,
        "description": "Quà tân thủ khi tham gia bot.",
    },
    "capcut_free": {
        "name": "CapCut Free",
        "platform": "TK Free",
        "type": "free",
        "duration_days": 30,
        "reward_type": "referral",
        "required_referrals": 2,
        "description": "Mời đủ 2 người mới tham gia bot để nhận.",
    },
    "chatgpt_free": {
        "name": "ChatGPT Free",
        "platform": "TK Free",
        "type": "free",
        "duration_days": 30,
        "reward_type": "referral",
        "required_referrals": 5,
        "description": "Mời đủ 5 người mới tham gia bot để nhận.",
    },
    "grok_free": {
        "name": "Grok Free",
        "platform": "TK Free",
        "type": "free",
        "duration_days": 30,
        "reward_type": "manual",
        "required_referrals": None,
        "description": "Gói quà sự kiện / admin cấp thủ công.",
    },
}

ALL_CATALOG = {**CATALOG, **FREE_CATALOG}

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
FIRST_PURCHASE_DISCOUNT = 0.20

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
        "support": "Telegram: @tkminer | Zalo: 0326805803",
        "bank_id": BANK_ID,
        "account_number": ACCOUNT_NUMBER,
    }


def default_inventory() -> Dict[str, Any]:
    return {code: [] for code in ALL_CATALOG}


def default_referrals() -> Dict[str, Any]:
    return {"referred_by": {}, "referrals": {}}


def default_free_claims() -> Dict[str, Any]:
    return {}


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
        (REFERRALS_FILE, default_referrals()),
        (FREE_CLAIMS_FILE, default_free_claims()),
        (CANVA_REQUESTS_FILE, {}),
    ]:
        if load_gist_json(filename, None) is None:
            save_gist_json(filename, default)

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


def get_users() -> Dict[str, Any]:
    return load_gist_json(USERS_FILE, {})


def save_users(data: Dict[str, Any]):
    save_gist_json(USERS_FILE, data)


def get_referrals() -> Dict[str, Any]:
    data = load_gist_json(REFERRALS_FILE, default_referrals())
    data.setdefault("referred_by", {})
    data.setdefault("referrals", {})
    return data


def save_referrals(data: Dict[str, Any]):
    save_gist_json(REFERRALS_FILE, data)


def get_free_claims() -> Dict[str, Any]:
    return load_gist_json(FREE_CLAIMS_FILE, default_free_claims())


def save_free_claims(data: Dict[str, Any]):
    save_gist_json(FREE_CLAIMS_FILE, data)

def get_canva_requests() -> Dict[str, Any]:
    return load_gist_json(CANVA_REQUESTS_FILE, {})


def save_canva_requests(data: Dict[str, Any]):
    save_gist_json(CANVA_REQUESTS_FILE, data)


def canva_request_id(user_id: int) -> str:
    return f"canva-{user_id}-{now_ts()}"


def find_latest_canva_request(user_id: int) -> Optional[Dict[str, Any]]:
    requests_data = get_canva_requests()
    items = [v for v in requests_data.values() if int(v.get("user_id", 0)) == int(user_id)]
    if not items:
        return None
    items.sort(key=lambda x: int(x.get("created_at", 0)), reverse=True)
    return items[0]


def canva_request_status_text(user_id: int) -> Optional[str]:
    req = find_latest_canva_request(user_id)
    if not req:
        return None
    status = req.get("status")
    email = req.get("email", "")
    if status == "pending_admin":
        return f"Đang chờ admin add mail {email}"
    if status == "success":
        return f"Đã add thành công mail {email}"
    if status == "out_of_stock":
        return f"Tạm hết suất cho mail {email}"
    return None


def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email or ""))



def user_ref_code(user_id: int) -> str:
    return f"ref_{user_id}"


def save_user(user_id: int, username: str, full_name: str):
    users = get_users()
    old = users.get(str(user_id), {})
    users[str(user_id)] = {
        "username": username,
        "full_name": full_name,
        "updated_at": now_ts(),
        "joined_at": old.get("joined_at", now_ts()),
        "ref_code": old.get("ref_code", user_ref_code(user_id)),
    }
    save_users(users)


def process_referral_join(new_user_id: int, start_param: str) -> Optional[int]:
    if not start_param.startswith("ref_"):
        return None
    try:
        referrer_id = int(start_param.split("_", 1)[1])
    except Exception:
        return None
    if referrer_id == new_user_id:
        return None

    referrals = get_referrals()
    referred_by = referrals.setdefault("referred_by", {})
    referred_map = referrals.setdefault("referrals", {})

    key = str(new_user_id)
    if key in referred_by:
        return None

    ref_key = str(referrer_id)
    referred_by[key] = referrer_id
    current = referred_map.get(ref_key, [])
    if new_user_id not in current:
        current.append(new_user_id)
    referred_map[ref_key] = current
    save_referrals(referrals)
    return referrer_id


def referral_count(user_id: int) -> int:
    referrals = get_referrals()
    return len(referrals.get("referrals", {}).get(str(user_id), []))


def referral_link(user_id: int) -> str:
    code = user_ref_code(user_id)
    if BOT_USERNAME:
        return f"https://t.me/{BOT_USERNAME}?start={code}"
    return f"Mã mời: {code}"


def claim_key(user_id: int, product_code: str) -> str:
    return f"{user_id}:{product_code}"


def has_claimed_free(user_id: int, product_code: str) -> bool:
    claims = get_free_claims()
    return claim_key(user_id, product_code) in claims


def mark_free_claimed(user_id: int, product_code: str, order_code: str):
    claims = get_free_claims()
    claims[claim_key(user_id, product_code)] = {
        "user_id": user_id,
        "product_code": product_code,
        "claimed_at": now_ts(),
        "order_code": order_code,
    }
    save_free_claims(claims)


def get_settings() -> Dict[str, Any]:
    settings = load_gist_json(SETTINGS_FILE, default_settings())
    for k, v in default_settings().items():
        settings.setdefault(k, v)
    return settings


def get_inventory() -> Dict[str, List[Dict[str, Any]]]:
    inventory = load_gist_json(INVENTORY_FILE, default_inventory())
    for code in ALL_CATALOG:
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
    if product_code == "canva_free":
        return "Add mail trực tiếp"
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


def has_paid_order(user_id: int) -> bool:
    orders = get_orders()
    for order in orders.values():
        if int(order.get("user_id", 0)) == int(user_id) and order.get("status") == "paid":
            if order.get("product_code") in CATALOG:
                return True
    return False


def is_first_purchase_discount_available(user_id: int) -> bool:
    return not has_paid_order(user_id)


def calculate_price_info(product_code: str, months: int = 1, user_id: Optional[int] = None) -> Dict[str, Any]:
    base_price = int(CATALOG[product_code]["price"])
    subtotal = base_price * months
    term_discount_rate = get_term_discount(months)
    after_term_discount = int(round(subtotal * (1 - term_discount_rate)))
    first_purchase_discount_rate = FIRST_PURCHASE_DISCOUNT if user_id and is_first_purchase_discount_available(user_id) else 0.0
    final_price = int(round(after_term_discount * (1 - first_purchase_discount_rate)))
    return {
        "base_monthly_price": base_price,
        "subtotal": subtotal,
        "term_discount_rate": term_discount_rate,
        "term_discount_percent": int(term_discount_rate * 100),
        "after_term_discount": after_term_discount,
        "first_purchase_discount_rate": first_purchase_discount_rate,
        "first_purchase_discount_percent": int(first_purchase_discount_rate * 100),
        "final_price": max(final_price, 0),
    }


def get_product_price(product_code: str, months: int = 1, user_id: Optional[int] = None) -> int:
    return calculate_price_info(product_code, months, user_id)["final_price"]


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
    product_meta = ALL_CATALOG[product_code]
    record = {
        "product_code": product_code,
        "product_name": product_meta["name"],
        "platform": product_meta["platform"],
        "type": product_meta["type"],
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


def get_totp_for_account_key(account_key: str) -> Optional[str]:
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
                tg_send_message(int(user_id), build_expiry_reminder_text(item, days_left))
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
# FREE REWARD HELPERS
# ============================================================
def free_product_requirement_text(product_code: str) -> str:
    item = FREE_CATALOG[product_code]
    req = item.get("required_referrals")
    if item.get("reward_type") == "join_bonus":
        return "Quà tân thủ: tham gia bot là nhận."
    if item.get("reward_type") in ("referral", "referral_points") and req is not None:
        return f"Yêu cầu: mời đủ {req} người mới tham gia bot."
    return item.get("description", "Đang cập nhật điều kiện.")


def is_free_reward_eligible(user_id: int, product_code: str) -> bool:
    item = FREE_CATALOG[product_code]
    reward_type = item.get("reward_type")
    if reward_type == "join_bonus":
        return True
    if reward_type in ("referral", "referral_points"):
        required = item.get("required_referrals") or 0
        return referral_count(user_id) >= required
    return False


def free_reward_progress(user_id: int, product_code: str) -> str:
    item = FREE_CATALOG[product_code]
    reward_type = item.get("reward_type")
    if reward_type == "join_bonus":
        return "Đủ điều kiện ngay"
    if reward_type in ("referral", "referral_points"):
        required = int(item.get("required_referrals") or 0)
        current = referral_count(user_id)
        return f"{current}/{required} người"
    return "Sự kiện/Admin"


def claim_free_reward(user_id: int, username: str, full_name: str, product_code: str) -> Dict[str, Any]:
    if product_code not in FREE_CATALOG:
        return {"ok": False, "message": "❌ Gói free không tồn tại."}
    if has_claimed_free(user_id, product_code):
        return {"ok": False, "message": "⚠️ Bạn đã nhận gói free này rồi."}
    if not is_free_reward_eligible(user_id, product_code):
        return {"ok": False, "message": f"⚠️ Bạn chưa đủ điều kiện. {free_product_requirement_text(product_code)}"}

    if product_code == "canva_free":
        latest = find_latest_canva_request(user_id)
        if latest and latest.get("status") == "pending_admin":
            return {"ok": False, "message": "⏳ Bạn đã gửi mail nhận Canva trước đó, vui lòng chờ admin xử lý."}
        return {"ok": True, "need_email": True, "message": "📨 Vui lòng gửi email Canva/Gmail bạn muốn nhận Canva Edu."}

    if not is_in_stock(product_code):
        return {"ok": False, "message": "⚠️ Kho quà free hiện đang hết, vui lòng quay lại sau."}

    account_data = allocate_inventory_account(product_code)
    if not account_data:
        return {"ok": False, "message": "⚠️ Kho quà free hiện đang hết, vui lòng quay lại sau."}

    order_code = f"free-{product_code}-{user_id}-{now_ts()}"
    duration_days = int(FREE_CATALOG[product_code].get("duration_days", 30))
    add_customer_product(
        user_id=user_id,
        username=username,
        full_name=full_name,
        product_code=product_code,
        account_data=account_data,
        duration_days=duration_days,
        order_code=order_code,
        delivered_by="free_reward",
    )
    mark_free_claimed(user_id, product_code, order_code)

    msg = (
        f"🎁 Bạn đã nhận thành công {FREE_CATALOG[product_code]['name']}\n\n"
        f"Tài khoản: {account_data.get('username', '')}\n"
        f"Mật khẩu: {account_data.get('password', '')}\n"
        f"Thời hạn: {duration_days} ngày"
    )
    if account_data.get("note"):
        msg += f"\nGhi chú: {account_data['note']}"
    if account_data.get("account_key"):
        msg += "\nBạn có thể vào mục 🔐 Lấy mã 2FA khi cần."
    return {"ok": True, "message": msg}

def create_canva_request(user_id: int, username: str, full_name: str, email: str) -> Dict[str, Any]:
    requests_data = get_canva_requests()
    request_id = canva_request_id(user_id)
    data = {
        "request_id": request_id,
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "email": email,
        "product_code": "canva_free",
        "status": "pending_admin",
        "created_at": now_ts(),
        "updated_at": now_ts(),
    }
    requests_data[request_id] = data
    save_canva_requests(requests_data)
    return data


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


def platform_menu_keyboard():
    rows = []
    for platform in ["ChatGPT", "Gemini", "Grok", "CapCut"]:
        rows.append([{"text": f"{platform}", "callback_data": f"platform|{platform}"}])
    rows.append([{"text": "⬅️ Về menu", "callback_data": "home"}])
    return {"inline_keyboard": rows}


def product_menu_keyboard(platform: str, user_id: int):
    rows = []
    for code in PLATFORM_TREE.get(platform, []):
        item = CATALOG[code]
        price = get_product_price(code, 1, user_id)
        title = f"{item['name']} - từ {format_money(price)}/tháng | {stock_label(code)}"
        rows.append([{
            "text": title,
            "callback_data": f"buy|{code}",
        }])
    rows.append([{"text": "⬅️ Chọn nền tảng khác", "callback_data": "menu_buy"}])
    return {"inline_keyboard": rows}


def free_menu_keyboard(user_id: int):
    rows = []
    for code in ["canva_free", "capcut_free", "chatgpt_free", "grok_free"]:
        name = FREE_CATALOG[code]["name"]
        progress = free_reward_progress(user_id, code)
        extra = "Add mail trực tiếp" if code == "canva_free" else stock_label(code)
        rows.append([{
            "text": f"{name} | {progress} | {extra}",
            "callback_data": f"freeinfo|{code}",
        }])
    rows.append([{"text": "👥 Mời bạn bè", "callback_data": "menu_invite"}])
    rows.append([{"text": "⬅️ Về menu", "callback_data": "home"}])
    return {"inline_keyboard": rows}


def free_detail_keyboard(user_id: int, product_code: str):
    rows = []
    can_claim = is_free_reward_eligible(user_id, product_code) and not has_claimed_free(user_id, product_code)
    if product_code == "canva_free":
        latest = find_latest_canva_request(user_id)
        latest_status = latest.get("status") if latest else ""
        if can_claim and latest_status not in ("pending_admin", "success"):
            rows.append([{"text": "📨 Gửi mail nhận Canva", "callback_data": f"claimfree|{product_code}"}])
    else:
        if can_claim and is_in_stock(product_code):
            rows.append([{"text": "🎁 Nhận ngay", "callback_data": f"claimfree|{product_code}"}])
    rows.append([{"text": "👥 Mời bạn bè", "callback_data": "menu_invite"}])
    rows.append([{"text": "⬅️ Về TK Free", "callback_data": "menu_free"}])
    return {"inline_keyboard": rows}


def term_menu_keyboard(product_code: str, user_id: int):
    rows = []
    stock = stock_label(product_code)
    for months in TERM_OPTIONS:
        total_price = get_product_price(product_code, months, user_id)
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


def admin_canva_request_keyboard(request_id: str):
    return {
        "inline_keyboard": [
            [{"text": "✅ Add thành công", "callback_data": f"canva_ok|{request_id}"}],
            [{"text": "⏳ Tạm hết", "callback_data": f"canva_empty|{request_id}"}],
        ]
    }


def active_2fa_keyboard(user_id: int):
    active = customer_active_items(user_id)
    rows = []
    for idx, item in enumerate(active):
        account_key = item.get("account", {}).get("account_key")
        if account_key:
            label = f"{item['product_name']} | {item.get('account', {}).get('username', 'N/A')}"
            rows.append([{"text": label[:60], "callback_data": f"get2fa|{idx}"}])
    if not rows:
        rows = [[{"text": "Chưa có gói hợp lệ", "callback_data": "noop"}]]
    rows.append([{"text": "⬅️ Về menu", "callback_data": "home"}])
    return {"inline_keyboard": rows}

# ============================================================
# MESSAGES
# ============================================================
def home_text() -> str:
    settings = get_settings()
    return (
        f"🎉 Chào mừng đến với {settings.get('shop_name', 'Trạm tài khoản số')}\n\n"
        "Bot hỗ trợ:\n"
        "- Mua tài khoản dùng chung / cấp riêng\n"
        "- Có menu TK Free theo mốc mời bạn bè\n"
        "- User mới mua lần đầu được giảm 20% cho 1 dịch vụ bất kỳ\n"
        "- Kiểm tra hạn sử dụng và chỉ cấp mã 2FA cho khách còn hạn\n\n"
        "🎁 Quà bot:\n"
        "- Tham gia bot: mở nhận Canva Edu miễn phí\n"
        "- Mời 2 người mới: nhận CapCut Free\n"
        "- Mời 5 người mới: nhận ChatGPT Free\n\n"
        "📞 Hỗ trợ:\n"
        "Telegram: @tkminer\n"
        "Zalo: 0326805803"
    )


def invite_text(user_id: int) -> str:
    count = referral_count(user_id)
    link = referral_link(user_id)
    return (
        "👥 Chương trình mời bạn bè\n\n"
        f"Bạn đã mời thành công: {count} người\n"
        f"Link / mã mời của bạn:\n{link}\n\n"
        "Mốc quà:\n"
        "- Tham gia bot: Canva Edu miễn phí\n"
        "- 2 người mới: CapCut Free\n"
        "- 5 người mới: ChatGPT Free\n"
        "- Grok Free: quà sự kiện / admin cấp thủ công\n\n"
        "Lưu ý: chỉ tính người mới chưa từng vào bot trước đó."
    )


def free_detail_text(user_id: int, product_code: str) -> str:
    item = FREE_CATALOG[product_code]
    claimed = has_claimed_free(user_id, product_code)
    eligible = is_free_reward_eligible(user_id, product_code)
    extra_status = canva_request_status_text(user_id) if product_code == "canva_free" else None
    status = extra_status or ("Đã nhận" if claimed else ("Có thể nhận ngay" if eligible else "Chưa đủ điều kiện"))
    extra_note = ""
    availability_line = f"Kho hiện tại: {stock_label(product_code)}"
    if product_code == "canva_free":
        availability_line = "Hình thức nhận: add mail trực tiếp, không dùng kho."
        extra_note = "\nLưu ý: khi nhận Canva Edu, bạn sẽ điền email. Bot sẽ gửi thông tin cho admin xử lý thủ công."
    return (
        f"🎁 {item['name']}\n\n"
        f"Điều kiện: {free_product_requirement_text(product_code)}\n"
        f"Tiến độ: {free_reward_progress(user_id, product_code)}\n"
        f"{availability_line}\n"
        f"Trạng thái: {status}\n\n"
        f"Mô tả: {item.get('description', '')}{extra_note}"
    )


def product_detail_text(product_code: str, months: int = 1, user_id: Optional[int] = None) -> str:
    item = CATALOG[product_code]
    type_vi = "Tài khoản dùng chung" if item["type"] == "shared" else "Tài khoản cấp riêng"
    duration_days = get_duration_days_for_months(months)
    price_info = calculate_price_info(product_code, months, user_id)
    lines = [
        f"📦 {item['name']}\n",
        f"Nền tảng: {item['platform']}",
        f"Loại: {type_vi}",
        f"Thời hạn đang chọn: {term_label(months)} ({duration_days} ngày)",
        f"Giá gốc theo kỳ hạn: {format_money(price_info['subtotal'])}",
    ]
    if price_info["term_discount_percent"] > 0:
        lines.append(f"Ưu đãi mua dài hạn: -{price_info['term_discount_percent']}%")
    if price_info["first_purchase_discount_percent"] > 0:
        lines.append(f"Ưu đãi khách mới lần đầu: -{price_info['first_purchase_discount_percent']}%")
    lines.extend([
        f"Giá thanh toán: {format_money(price_info['final_price'])}",
        f"Kho hiện tại: {stock_label(product_code)}",
        "",
        "Sau khi thanh toán và được xác nhận, bot sẽ cấp tài khoản hoặc ghi nhận để admin cấp riêng.",
        "Mã 2FA chỉ lấy được khi gói còn hạn.",
    ])
    return "\n".join(lines)


def my_products_text(user_id: int) -> str:
    items = customer_all_items(user_id)
    count = referral_count(user_id)
    lines = [
        f"👥 Điểm mời bạn bè: {count}",
        f"🎁 Link / mã mời: {referral_link(user_id)}",
        "",
    ]
    if not items:
        lines.append("📦 Bạn chưa có gói nào được kích hoạt.")
        return "\n".join(lines)

    current = now_ts()
    lines.append("📦 Danh sách gói của bạn:\n")
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

# ============================================================
# ORDER PROCESSING
# ============================================================
def create_pending_order(user_id: int, chat_id: int, username: str, full_name: str, product_code: str, months: int = 1) -> Dict[str, Any]:
    orders = get_pending_orders()
    order_code = make_payment_code(product_code, user_id)
    price_info = calculate_price_info(product_code, months, user_id)
    duration_days = get_duration_days_for_months(months)
    orders[order_code] = {
        "order_code": order_code,
        "user_id": user_id,
        "chat_id": chat_id,
        "username": username,
        "full_name": full_name,
        "product_code": product_code,
        "months": months,
        "price": price_info["final_price"],
        "base_monthly_price": int(CATALOG[product_code]["price"]),
        "subtotal": price_info["subtotal"],
        "term_discount_percent": price_info["term_discount_percent"],
        "first_purchase_discount_percent": price_info["first_purchase_discount_percent"],
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
            if account_data.get("account_key"):
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
        "/addstock <product_code> <username> <password> [account_key] [note]\n"
        "/addsecret <account_key> <base32_secret>\n"
        "/delsecret <account_key>\n"
        "/grant <user_id> <product_code> <days> <username> <password> [account_key]\n"
        "/grantfree <user_id> <free_product_code> <username> <password> [account_key]\n"
        "/setprice <product_code> <price>\n"
        "/orders\n"
        "/inventory\n"
        "/products\n"
        "/checkstock [product_code]\n"
        "/refstats [user_id]\n"
        "/remindnow\n"
        "Canva request sẽ có nút duyệt trực tiếp trong chat admin."
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
        lines.append("\n🎁 Free product code:")
        for code, item in FREE_CATALOG.items():
            lines.append(f"- {code}: {item['name']} | {free_product_requirement_text(code)} | {("Add mail trực tiếp" if code == "canva_free" else stock_label(code))}")
        tg_send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/checkstock":
        if len(parts) >= 2:
            code = parts[1]
            if code not in ALL_CATALOG:
                tg_send_message(chat_id, "❌ product_code không tồn tại.")
                return
            tg_send_message(chat_id, f"📦 {code} | {ALL_CATALOG[code]['name']} | " + ("Canva add mail trực tiếp, không dùng kho" if code == "canva_free" else f"Còn {get_stock_count(code)} tài khoản"))
            return
        lines = ["📦 Kiểm tra kho hiện tại:"]
        for code, item in ALL_CATALOG.items():
            lines.append(f"- {code}: {item['name']} | " + ("Add mail trực tiếp" if code == "canva_free" else stock_label(code)))
        tg_send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/refstats":
        target = user_id
        if len(parts) >= 2:
            try:
                target = int(parts[1])
            except ValueError:
                tg_send_message(chat_id, "❌ user_id không hợp lệ.")
                return
        tg_send_message(chat_id, f"👥 User {target} đã mời thành công {referral_count(target)} người.")
        return

    if cmd == "/remindnow":
        result = process_expiry_reminders()
        tg_send_message(chat_id, f"✅ Đã chạy nhắc hạn. Ngày: {result['date']} | Đã gửi: {result['sent_count']} | Bỏ qua: {result['skipped']}")
        return

    if cmd == "/inventory":
        inventory = get_inventory()
        lines = ["📦 Tồn kho:"]
        for code, rows in inventory.items():
            lines.append(f"- {code}: " + ("Canva add mail trực tiếp, không dùng kho" if code == "canva_free" else f"{len(rows)} tài khoản | {stock_label(code)}"))
        tg_send_message(chat_id, "\n".join(lines))
        return

    if cmd == "/orders":
        pending = get_pending_orders()
        if not pending:
            tg_send_message(chat_id, "Không có đơn chờ.")
            return
        lines = ["🧾 Đơn đang chờ:"]
        for k, v in pending.items():
            lines.append(
                f"- {k} | {v['product_code']} | {term_label(int(v.get('months', 1)))} | {v.get('username','')} | {format_money(v['price'])}"
            )
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
            tg_send_message(chat_id, "❌ product_code không tồn tại hoặc không phải gói trả phí.")
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
        if product_code not in ALL_CATALOG:
            tg_send_message(chat_id, "❌ product_code không tồn tại.")
            return
        username = parts[2]
        password = parts[3]
        account_key = parts[4] if len(parts) >= 5 else ""
        note = " ".join(parts[5:]) if len(parts) >= 6 else ""
        add_inventory_account(product_code, username, password, account_key, note)
        tg_send_message(chat_id, f"✅ Đã thêm kho cho {product_code}. Tồn kho hiện tại: {get_stock_count(product_code)}")
        return

    if cmd == "/grantfree" and len(parts) >= 5:
        try:
            target_user_id = int(parts[1])
        except ValueError:
            tg_send_message(chat_id, "❌ user_id không hợp lệ.")
            return
        product_code = parts[2]
        if product_code not in FREE_CATALOG:
            tg_send_message(chat_id, "❌ free_product_code không tồn tại.")
            return
        username_acc = parts[3]
        password_acc = parts[4]
        account_key = parts[5] if len(parts) >= 6 else ""
        users = get_users()
        user_info = users.get(str(target_user_id), {})
        order_code = f"manual-free-{int(time.time())}"
        add_customer_product(
            user_id=target_user_id,
            username=user_info.get("username", ""),
            full_name=user_info.get("full_name", ""),
            product_code=product_code,
            account_data={
                "username": username_acc,
                "password": password_acc,
                "account_key": account_key,
            },
            duration_days=int(FREE_CATALOG[product_code].get("duration_days", 30)),
            order_code=order_code,
            delivered_by="admin_free",
        )
        mark_free_claimed(target_user_id, product_code, order_code)
        tg_send_message(chat_id, f"✅ Đã cấp free thủ công cho user {target_user_id}.")
        tg_send_message(target_user_id, f"🎁 Admin đã cấp cho bạn: {FREE_CATALOG[product_code]['name']}\nTài khoản: {username_acc}\nMật khẩu: {password_acc}")
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
        account_key = parts[6] if len(parts) >= 7 else ""
        users = get_users()
        user_info = users.get(str(target_user_id), {})
        record = add_customer_product(
            user_id=target_user_id,
            username=user_info.get("username", ""),
            full_name=user_info.get("full_name", ""),
            product_code=product_code,
            account_data={
                "username": username_acc,
                "password": password_acc,
                "account_key": account_key,
            },
            duration_days=days,
            order_code=f"manual-{int(time.time())}",
            delivered_by="admin",
        )
        tg_send_message(chat_id, f"✅ Đã cấp thủ công cho user {target_user_id}. Hết hạn: {format_expiry(record['expires_at'])}")
        tg_send_message(target_user_id,
                        f"🎁 Admin đã cấp cho bạn: {CATALOG[product_code]['name']}\n"
                        f"Tài khoản: {username_acc}\nMật khẩu: {password_acc}\n"
                        f"Hết hạn: {format_expiry(record['expires_at'])}")
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


def process_start(chat_id: int, user_id: int, username: str, full_name: str, text: str):
    users = get_users()
    is_first_join = str(user_id) not in users
    save_user(user_id, username, full_name)

    start_param = ""
    parts = text.split(maxsplit=1)
    if len(parts) > 1:
        start_param = parts[1].strip()

    referral_msg = ""
    if start_param:
        referrer_id = process_referral_join(user_id, start_param)
        if referrer_id:
            referral_msg = "\n\n🎉 Bạn đã tham gia bot qua link mời hợp lệ."
            tg_send_message(referrer_id, f"🎉 Bạn vừa mời thành công 1 người mới. Tổng hiện tại: {referral_count(referrer_id)} người.")

    welcome_bonus_msg = ""
    if is_first_join:
        welcome_bonus_msg = (
            "\n\n🎁 Quà tân thủ đã mở:\n"
            "- Bạn có thể vào menu TK Free để gửi mail nhận Canva Edu miễn phí.\n"
            "- Lần mua dịch vụ trả phí đầu tiên của bạn sẽ tự giảm 20%."
        )

    tg_send_message(chat_id, home_text() + referral_msg + welcome_bonus_msg, reply_markup=main_menu_keyboard())


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
        tg_edit_message(chat_id, message_id, "🎁 Chọn tài khoản free:", reply_markup=free_menu_keyboard(user_id))
        return
    if data == "menu_invite":
        tg_edit_message(chat_id, message_id, invite_text(user_id), reply_markup=free_menu_keyboard(user_id))
        return
    if data == "menu_my":
        tg_edit_message(chat_id, message_id, my_products_text(user_id), reply_markup=main_menu_keyboard())
        return
    if data == "menu_2fa":
        tg_edit_message(chat_id, message_id, "🔐 Chọn tài khoản còn hạn để lấy mã 2FA.\nKhách hết hạn sẽ không lấy được mã.", reply_markup=active_2fa_keyboard(user_id))
        return
    if data.startswith("platform|"):
        platform = data.split("|", 1)[1]
        tg_edit_message(chat_id, message_id, f"🛒 {platform} - chọn gói:", reply_markup=product_menu_keyboard(platform, user_id))
        return
    if data.startswith("buy|"):
        code = data.split("|", 1)[1]
        tg_edit_message(chat_id, message_id, product_detail_text(code, 1, user_id), reply_markup=term_menu_keyboard(code, user_id))
        return
    if data.startswith("term|"):
        _, code, months_raw = data.split("|", 2)
        months = int(months_raw)
        tg_edit_message(chat_id, message_id, product_detail_text(code, months, user_id), reply_markup=confirm_buy_keyboard(code, months))
        return
    if data.startswith("freeinfo|"):
        code = data.split("|", 1)[1]
        tg_edit_message(chat_id, message_id, free_detail_text(user_id, code), reply_markup=free_detail_keyboard(user_id, code))
        return
    if data.startswith("claimfree|"):
        code = data.split("|", 1)[1]
        result = claim_free_reward(user_id, username, full_name, code)
        if result.get("need_email"):
            USER_STATE[user_id] = {"awaiting_canva_email": True, "free_product_code": code}
        tg_send_message(chat_id, result["message"])
        if message_id:
            tg_edit_message(chat_id, message_id, "🎁 Chọn tài khoản free:", reply_markup=free_menu_keyboard(user_id))
        return
    if data.startswith("pay|"):
        _, code, months_raw = data.split("|", 2)
        months = int(months_raw)
        if CATALOG[code]["type"] == "shared" and not is_in_stock(code):
            tg_send_message(chat_id, "⚠️ Sản phẩm này hiện đã hết kho, vui lòng chọn gói khác.")
            return
        order = create_pending_order(user_id, chat_id, username, full_name, code, months)
        qr_url = generate_qr(order["price"], order["order_code"])
        caption_lines = [
            f"🧾 Mã đơn: {order['order_code']}",
            f"Gói: {CATALOG[code]['name']}",
            f"Thời hạn: {term_label(months)} ({order['duration_days']} ngày)",
            f"Tạm tính: {format_money(order['subtotal'])}",
        ]
        if int(order.get("term_discount_percent", 0)) > 0:
            caption_lines.append(f"Ưu đãi dài hạn: -{order['term_discount_percent']}%")
        if int(order.get("first_purchase_discount_percent", 0)) > 0:
            caption_lines.append(f"Ưu đãi khách mới lần đầu: -{order['first_purchase_discount_percent']}%")
        caption_lines.extend([
            f"Số tiền cần chuyển: {format_money(order['price'])}",
            "",
            "1. Quét QR để thanh toán",
            "2. Chuyển đúng nội dung",
            "3. Bấm 'Tôi đã chuyển khoản'",
            "4. Chờ admin xác nhận",
        ])
        tg_send_photo(chat_id, qr_url, caption="\n".join(caption_lines), reply_markup=payment_confirm_keyboard(order["order_code"]))
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
        account_key = items[idx].get("account", {}).get("account_key")
        if not account_key:
            tg_send_message(chat_id, "⚠️ Tài khoản này chưa được cấu hình 2FA.")
            return
        code = get_totp_for_account_key(account_key)
        if not code:
            tg_send_message(chat_id, "⚠️ Không lấy được mã 2FA. Kiểm tra cấu hình secret.")
            return
        tg_send_message(chat_id, f"🔐 Mã 2FA: {code}\nTài khoản: {items[idx].get('account', {}).get('username', '')}\nHết hạn: {format_expiry(int(items[idx]['expires_at']))}")
        return
    if data.startswith("canva_ok|"):
        if not is_admin(user_id):
            tg_send_message(chat_id, "❌ Bạn không phải admin.")
            return
        request_id = data.split("|", 1)[1]
        requests_data = get_canva_requests()
        req = requests_data.get(request_id)
        if not req:
            tg_send_message(chat_id, "❌ Không tìm thấy yêu cầu Canva.")
            return
        if req.get("status") == "success":
            tg_send_message(chat_id, "ℹ️ Yêu cầu này đã được duyệt trước đó.")
            return
        req["status"] = "success"
        req["updated_at"] = now_ts()
        requests_data[request_id] = req
        save_canva_requests(requests_data)
        duration_days = int(FREE_CATALOG["canva_free"].get("duration_days", 30))
        order_code = f"free-canva-approved-{req['user_id']}-{now_ts()}"
        add_customer_product(
            user_id=int(req["user_id"]),
            username=req.get("username", ""),
            full_name=req.get("full_name", ""),
            product_code="canva_free",
            account_data={"username": req.get("email", ""), "password": "", "note": "Canva Edu add qua email"},
            duration_days=duration_days,
            order_code=order_code,
            delivered_by="admin_canva_email",
        )
        mark_free_claimed(int(req["user_id"]), "canva_free", order_code)
        tg_send_message(
            int(req["user_id"]),
            "🎉 Admin đã add Canva Edu thành công cho email của bạn.\n\n"
            f"Email: {req.get('email', '')}\n"
            "Vui lòng kiểm tra hòm thư và đăng nhập lại Canva sau ít phút."
        )
        tg_send_message(chat_id, f"✅ Đã duyệt Canva thành công cho user {req['user_id']} | {req.get('email','')}")
        return
    if data.startswith("canva_empty|"):
        if not is_admin(user_id):
            tg_send_message(chat_id, "❌ Bạn không phải admin.")
            return
        request_id = data.split("|", 1)[1]
        requests_data = get_canva_requests()
        req = requests_data.get(request_id)
        if not req:
            tg_send_message(chat_id, "❌ Không tìm thấy yêu cầu Canva.")
            return
        req["status"] = "out_of_stock"
        req["updated_at"] = now_ts()
        requests_data[request_id] = req
        save_canva_requests(requests_data)
        tg_send_message(
            int(req["user_id"]),
            "⏳ Hiện Canva Edu free đang tạm hết suất xử lý.\n\n"
            f"Mail bạn đã gửi: {req.get('email', '')}\n"
            "Khi có đợt add tiếp theo, bạn có thể gửi lại yêu cầu trong menu TK Free."
        )
        tg_send_message(chat_id, f"⏳ Đã đánh dấu tạm hết cho user {req['user_id']} | {req.get('email','')}")
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

    state = USER_STATE.get(user_id, {})
    if state.get("awaiting_canva_email"):
        email = text.strip()
        if not is_valid_email(email):
            tg_send_message(chat_id, "⚠️ Email chưa đúng định dạng. Vui lòng nhập lại email hợp lệ để nhận Canva Edu.")
            return
        latest = find_latest_canva_request(user_id)
        if latest and latest.get("status") == "pending_admin":
            USER_STATE.pop(user_id, None)
            tg_send_message(chat_id, "⏳ Bạn đã có một yêu cầu Canva đang chờ admin xử lý.")
            return
        request_data = create_canva_request(user_id, username, full_name, email)
        USER_STATE.pop(user_id, None)
        tg_send_message(
            chat_id,
            "✅ Bot đã ghi nhận email nhận Canva Edu của bạn.\n\n"
            f"Email: {email}\n"
            "Admin sẽ xử lý thủ công sớm nhất. Khi có kết quả, bot sẽ nhắn lại cho bạn."
        )
        send_admin_message(
            "📨 Yêu cầu Canva Edu free mới\n"
            f"- User: @{username} | ID: {user_id}\n"
            f"- Tên: {full_name or '(không có)'}\n"
            f"- Email cần add: {email}\n"
            f"- Request ID: {request_data['request_id']}",
            reply_markup=admin_canva_request_keyboard(request_data["request_id"]),
        )
        return

    if text.startswith("/"):
        if text.startswith(("/admin", "/addstock", "/addsecret", "/delsecret", "/grant", "/grantfree", "/setprice", "/inventory", "/orders", "/products", "/checkstock", "/refstats", "/remindnow")):
            handle_admin_command(chat_id, user_id, text)
            return
        if text.startswith("/start"):
            process_start(chat_id, user_id, username, full_name, text)
            return
        if text.startswith("/my"):
            tg_send_message(chat_id, my_products_text(user_id), reply_markup=main_menu_keyboard())
            return
        if text.startswith("/invite"):
            tg_send_message(chat_id, invite_text(user_id), reply_markup=free_menu_keyboard(user_id))
            return
        if text.startswith("/free"):
            tg_send_message(chat_id, "🎁 Chọn tài khoản free:", reply_markup=free_menu_keyboard(user_id))
            return
        if text.startswith("/2fa"):
            tg_send_message(chat_id, "🔐 Chọn trong menu để lấy mã 2FA.", reply_markup=active_2fa_keyboard(user_id))
            return

    active = customer_active_items(user_id)
    direct = next((x for x in active if x.get("account", {}).get("account_key") == text), None)
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
        "free_catalog_size": len(FREE_CATALOG),
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
