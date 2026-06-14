"""
Authentication module: bcrypt password hashing, JWT token management,
and FastAPI dependency injection for current user / admin user.
"""

from __future__ import annotations

import os
import secrets
import warnings
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", secrets.token_hex(32))
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "24"))
JWT_ALGORITHM = "HS256"

if not os.environ.get("JWT_SECRET_KEY"):
    warnings.warn(
        "JWT_SECRET_KEY not set. Using random key — all tokens invalid on restart.",
        RuntimeWarning,
    )


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Returns the hash as a string."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, username: str, is_admin: bool) -> str:
    """Create a JWT access token with user claims."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "is_admin": is_admin,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token. Raises on invalid/expired token."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency: extract and validate JWT from Authorization header or ?token query param.

    The query param fallback exists for EventSource (SSE) which doesn't support custom headers.

    Returns a dict with keys: user_id, username, is_admin.
    Raises HTTPException(401) on missing/invalid token.
    """
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication")

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "user_id": payload["sub"],
        "username": payload["username"],
        "is_admin": payload.get("is_admin", False),
    }


async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency: require admin role on top of valid auth.

    Returns the same user dict as get_current_user.
    Raises HTTPException(403) if user is not admin.
    """
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
