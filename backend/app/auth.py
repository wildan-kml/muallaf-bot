"""Password hashing and signed access tokens without storing browser secrets."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets
from typing import Any

from fastapi import Header, HTTPException

from .config import get_settings
from .database import Database


PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (TypeError, ValueError):
        return False


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_access_token(user_id: str, username: str, secret: str, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    header = _b64_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64_encode(
        json.dumps(
            {
                "sub": user_id,
                "username": username,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=minutes)).timestamp()),
                "jti": secrets.token_hex(8),
            },
            separators=(",", ":"),
        ).encode()
    )
    signature = _b64_encode(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    try:
        header, payload, signature = token.split(".", 2)
        expected = _b64_encode(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        claims = json.loads(_b64_decode(payload))
        if int(claims.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expired")
        if not claims.get("sub"):
            raise ValueError("missing subject")
        return claims
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Sesi login tidak valid atau sudah berakhir") from exc


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    username: str
    display_name: str
    role: str


def get_current_user(authorization: str | None = Header(default=None)) -> AuthenticatedUser:
    settings = get_settings()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Silakan login terlebih dahulu")
    claims = decode_access_token(authorization.split(" ", 1)[1].strip(), settings.jwt_secret)
    user = Database(settings.database_url, settings.chat_retention_days).get_user_by_id(str(claims["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="Akun tidak ditemukan")
    return AuthenticatedUser(
        id=user["id"],
        username=user["username"],
        display_name=user["display_name"],
        role=user["role"],
    )


def require_admin(user: AuthenticatedUser) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Akses admin diperlukan")

