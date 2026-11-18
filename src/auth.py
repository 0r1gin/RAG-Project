import hmac
import os
import time

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from dotenv import load_dotenv
from fastapi import Cookie, HTTPException, Request, Response

load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

COOKIE_NAME = "admin_token"
TOKEN_MINUTES = 30

if not (ADMIN_USERNAME and ADMIN_PASSWORD_HASH and len(JWT_SECRET) >= 32):
    raise RuntimeError(
        "Set ADMIN_USERNAME, ADMIN_PASSWORD_HASH and a JWT_SECRET of 32+ characters in .env"
    )

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("not-the-password")   # keeps timing similar when the username is wrong


# ---------- credentials ----------
def check_credentials(username: str, password: str) -> bool:
    user_ok = hmac.compare_digest(username.encode(), ADMIN_USERNAME.encode())
    try:
        _hasher.verify(ADMIN_PASSWORD_HASH if user_ok else _DUMMY_HASH, password)
        password_ok = True
    except (VerificationError, InvalidHashError):
        password_ok = False
    return user_ok and password_ok


# ---------- session token ----------
def issue_token(response: Response):
    now = int(time.time())
    token = jwt.encode(
        {"sub": ADMIN_USERNAME, "iat": now, "exp": now + TOKEN_MINUTES * 60},
        JWT_SECRET,
        algorithm="HS256",
    )
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=TOKEN_MINUTES * 60,
        httponly=True, samesite="strict", secure=COOKIE_SECURE, path="/",
    )


def require_admin(admin_token: str | None = Cookie(default=None)) -> str:
    """FastAPI dependency: attach to any route only the admin may call."""
    if not admin_token:
        raise HTTPException(401, "Not logged in")
    try:
        payload = jwt.decode(admin_token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired, please log in again")
    if payload.get("sub") != ADMIN_USERNAME:
        raise HTTPException(401, "Invalid session")
    return payload["sub"]


# ---------- rate limiting (in memory, per IP) ----------
MAX_FAILURES = 5
WINDOW_SECONDS = 10
_failures: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    # Behind a host's proxy, the real client is the LAST X-Forwarded-For entry.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _recent(ip: str) -> list[float]:
    cutoff = time.time() - WINDOW_SECONDS
    recent = [t for t in _failures.get(ip, []) if t > cutoff]
    _failures[ip] = recent
    return recent


def check_rate_limit(request: Request):
    if len(_recent(_client_ip(request))) >= MAX_FAILURES:
        raise HTTPException(429, "Too many failed attempts. Try again in 10 seconds.")


def record_failure(request: Request):
    _recent(_client_ip(request)).append(time.time())


def clear_failures(request: Request):
    _failures.pop(_client_ip(request), None)