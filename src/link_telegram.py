"""One-time setup: finds the chat id of the Telegram account named in ADMIN_TELEGRAM_HANDLE."""
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
HANDLE = os.environ["ADMIN_TELEGRAM_HANDLE"].lstrip("@").lower()

try:
    data = httpx.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", timeout=15).json()
except httpx.HTTPError:
    sys.exit("Could not reach Telegram")
if not data.get("ok"):
    sys.exit(f"Telegram rejected the request: {data.get('description')}")

for update in data["result"]:
    message = update.get("message") or {}
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    if (sender.get("username") or "").lower() == HANDLE and chat.get("type") == "private":
        print(f"Found @{HANDLE}. Add this line to .env:")
        print(f"TELEGRAM_ADMIN_CHAT_ID={chat['id']}")
        break
else:
    sys.exit(f"No message from @{HANDLE} yet. Open your bot, press Start, then run this again.")