from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.core.config import settings


def _secret() -> bytes:
    return f"{settings.admin_id}:{settings.admin_pwd}".encode()


def create_admin_token() -> tuple[str, int]:
    exp = int(time.time()) + 12 * 3600
    payload = json.dumps({"exp": exp, "role": "admin"}, separators=(",", ":"))
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()
    return token, exp


def verify_admin_token(token: str) -> bool:
    if not token or not settings.admin_configured:
        return False
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = raw.rsplit("|", 1)
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        data = json.loads(payload)
        return data.get("role") == "admin" and int(data.get("exp", 0)) > time.time()
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return False
