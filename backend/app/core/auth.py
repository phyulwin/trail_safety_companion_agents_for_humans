# core/auth.py - Argon2 passwords and revocable JWTs in HttpOnly cookies.
import time
from collections import defaultdict, deque
import jwt
from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db
from app.models import User

passwords = PasswordHash.recommended()
attempts: dict[str, deque] = defaultdict(deque)


def throttle(request: Request) -> None:
    """Bound local login attempts; production needs a distributed rate limiter."""
    key = request.client.host if request.client else "unknown"
    window = attempts[key]
    now = time.time()
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= 30:
        raise HTTPException(429, "Too many attempts; try again in one minute")
    window.append(now)


def issue_token(user: User) -> str:
    """Include revocation version, expiry, audience, and issuer."""
    return jwt.encode({"sub": user.id, "ver": user.token_version, "exp": int(time.time()) + 28800,
                       "iat": int(time.time()), "aud": "trail", "iss": "trail-api"}, settings.jwt_secret, algorithm="HS256")


def resolve_token(token: str | None, db: Session) -> User:
    """Reject expired, revoked, malformed, or wrong-audience tokens uniformly."""
    try:
        data = jwt.decode(token or "", settings.jwt_secret, algorithms=["HS256"], audience="trail", issuer="trail-api")
        user = db.get(User, data["sub"])
        if not user or user.token_version != data.get("ver"):
            raise ValueError("revoked")
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Please sign in") from None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Use HttpOnly cookies for browsers and optional bearer tokens for scripts."""
    header = request.headers.get("authorization", "")
    token = header[7:] if header.startswith("Bearer ") else request.cookies.get("trail_token")
    return resolve_token(token, db)
