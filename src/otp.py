import os
import secrets
import threading
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
HANDLE = os.getenv("ADMIN_TELEGRAM_HANDLE", "").lstrip("@").lower()
try:
    CHAT_ID = int(os.getenv("TELEGRAM_ADMIN_CHAT_ID", ""))
except ValueError:
    CHAT_ID = None

if not (BOT_TOKEN and HANDLE and CHAT_ID):
    raise RuntimeError(
        "Set TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_HANDLE and TELEGRAM_ADMIN_CHAT_ID in .env "
        "(run: python src/cli.py link-telegram)"
    )

OTP_TTL_SECONDS = 300
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 30

_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
_lock = threading.Lock()
_challenges: dict[str, dict] = {}   # in memory: correct for ONE server process only
_last_sent = 0.0


class OtpCooldown(Exception):
    pass


def _call(method: str, **params) -> dict:
    # httpx error messages contain the full URL, which contains the bot token,
    # so never let those exceptions escape or reach the logs.
    try:
        response = httpx.post(f"{_API}/{method}", json=params, timeout=10)
        data = response.json()
    except (httpx.HTTPError, ValueError):
        raise RuntimeError("Could not reach Telegram")
    if not data.get("ok"):
        raise RuntimeError(f"Telegram error: {data.get('description', 'unknown')}")
    return data["result"]


def verify_link():
    """Startup check: the stored chat id must still belong to the configured handle."""
    try:
        chat = _call("getChat", chat_id=CHAT_ID)
    except RuntimeError as e:
        print(f"WARNING: could not verify the Telegram link ({e})")
        return
    if (chat.get("username") or "").lower() != HANDLE:
        raise RuntimeError(
            "TELEGRAM_ADMIN_CHAT_ID does not belong to ADMIN_TELEGRAM_HANDLE. "
            "Re-run: python src/cli.py link-telegram"
        )


def start_challenge() -> str:
    """Send a code to the admin's Telegram and return a challenge id for the browser."""
    global _last_sent
    with _lock:
        now = time.time()
        if now - _last_sent < RESEND_COOLDOWN_SECONDS:
            raise OtpCooldown()

        code = f"{secrets.randbelow(10**6):06d}"
        _call(
            "sendMessage",
            chat_id=CHAT_ID,
            text=(
                f"Your doc-chat admin code is {code}. It expires in 5 minutes. "
                "If this wasn't you, change your admin password."
            ),
        )
        _last_sent = now

        _challenges.clear()                      # single admin: only the newest code is valid
        challenge_id = secrets.token_urlsafe(24)
        _challenges[challenge_id] = {"code": code, "expires": now + OTP_TTL_SECONDS, "attempts": 0}
        return challenge_id


def verify_challenge(challenge_id: str, code: str) -> bool:
    with _lock:
        challenge = _challenges.get(challenge_id)
        if not challenge:
            return False
        if time.time() > challenge["expires"]:
            _challenges.pop(challenge_id, None)
            return False

        challenge["attempts"] += 1
        if secrets.compare_digest(challenge["code"], code):
            _challenges.pop(challenge_id, None)  # single use
            return True
        if challenge["attempts"] >= MAX_ATTEMPTS:
            _challenges.pop(challenge_id, None)  # too many guesses: the code is dead
        return False