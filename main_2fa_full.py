
import json
import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import pyotp

app = FastAPI()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GIST_ID = os.getenv("GIST_ID")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}


def load_secrets():
    url = f"https://api.github.com/gists/{GIST_ID}"
    r = requests.get(url, headers=HEADERS)
    files = r.json().get("files", {})
    content = files.get("secrets.json", {}).get("content", "{}")
    return json.loads(content)


def save_secrets(secrets):
    url = f"https://api.github.com/gists/{GIST_ID}"
    data = {
        "files": {
            "secrets.json": {
                "content": json.dumps(secrets, indent=4)
            }
        }
    }
    requests.patch(url, headers=HEADERS, json=data)


@app.post("/webhook")
async def handle_message(request: Request):
    body = await request.json()
    message = body.get("message", {}).get("text", "")
    chat_id = body.get("message", {}).get("chat", {}).get("id", "")
    secrets = load_secrets()

    reply = "Xin chào"
    command, *args = message.strip().split()

    if command.lower() == "add" and len(args) == 2:
        email, secret = args
        secrets[email] = secret
        save_secrets(secrets)
        reply = "✅ Thêm thành công"
    elif command.lower() == "edit" and len(args) == 2:
        email, secret = args
        if email in secrets:
            secrets[email] = secret
            save_secrets(secrets)
            reply = "✅ Sửa thành công"
        else:
            reply = "❌ Không tồn tại email"
    elif command.lower() == "delete" and len(args) == 1:
        email = args[0]
        if email in secrets:
            del secrets[email]
            save_secrets(secrets)
            reply = "✅ Xoá thành công"
        else:
            reply = "❌ Không tồn tại email"
    elif "@" in message:
        email = message.strip()
        if email in secrets:
            totp = pyotp.TOTP(secrets[email])
            reply = f"⏱ Mã 2FA: {totp.now()}"
        else:
            reply = "❌ Không tìm thấy secret cho email này"

    token = os.getenv("BOT_TOKEN")
    telegram_url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(telegram_url, json={"chat_id": chat_id, "text": reply})

    return PlainTextResponse("OK")
