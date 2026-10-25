"""Password hashing and JWT helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from .config import settings

# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256; no external deps required).
# ---------------------------------------------------------------------------
_PBKDF2_ROUNDS = 240_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Minimal JWT (HS256) implementation.
# ---------------------------------------------------------------------------
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(subject: str, claims: dict[str, Any] | None = None) -> str:
    header = {"alg": settings.ALGORITHM, "typ": "JWT"}
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
    if claims:
        payload.update(claims)

    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode()
    signature = hmac.new(
        settings.SECRET_KEY.encode(), signing_input, hashlib.sha256
    ).digest()
    segments.append(_b64url_encode(signature))
    return ".".join(segments)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected = hmac.new(
            settings.SECRET_KEY.encode(), signing_input, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64url_decode(sig_b64), expected):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
