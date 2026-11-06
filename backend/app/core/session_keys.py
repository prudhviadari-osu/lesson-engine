"""In-memory, per-session API keys (never written to disk or DB).

Users paste their own Gemini / YouTube key on the account-settings page; we hold
it ONLY in process memory, keyed by user id, for as long as the server runs.
Logging out clears it, and a server restart wipes everything — so no secret is
ever persisted. This is deliberately NOT the DB (keys are secrets).

Resolution order for "what key do we use for this user":
  1. The demo account is ALWAYS mock — it ignores any key entirely.
  2. A key the user pasted this session (held here).
  3. A server-wide GEMINI_API_KEY from the environment, IF present (optional).
  4. Otherwise: no key -> offline mock.
"""
from __future__ import annotations

import threading

from .config import settings

# Email of the permanent demo account: always mock, preloaded content, no key.
DEMO_ACCOUNT_EMAIL = "buckeye.1@osu.edu"

_lock = threading.Lock()
# user_id -> {"gemini": str|None, "youtube": str|None}
_keys: dict[int, dict[str, str | None]] = {}


def set_keys(user_id: int, *, gemini: str | None = None, youtube: str | None = None) -> None:
    """Store (or update) this user's session keys. Empty string clears a key."""
    with _lock:
        cur = _keys.setdefault(user_id, {"gemini": None, "youtube": None})
        if gemini is not None:
            cur["gemini"] = gemini.strip() or None
        if youtube is not None:
            cur["youtube"] = youtube.strip() or None


def clear_keys(user_id: int) -> None:
    with _lock:
        _keys.pop(user_id, None)


def _session(user_id: int | None) -> dict[str, str | None]:
    if user_id is None:
        return {"gemini": None, "youtube": None}
    with _lock:
        return dict(_keys.get(user_id, {"gemini": None, "youtube": None}))


def is_demo_account(user: dict | None) -> bool:
    return bool(user) and (user.get("email") == DEMO_ACCOUNT_EMAIL)


def gemini_key_for(user: dict | None) -> str | None:
    """The effective Gemini key for this user, or None (-> mock)."""
    if is_demo_account(user):
        return None  # demo account is always mock
    uid = user.get("id") if user else None
    sess = _session(uid)["gemini"]
    if sess:
        return sess
    # Optional server-wide fallback (not required; blank by default now).
    return settings.GEMINI_API_KEY or None


def youtube_key_for(user: dict | None) -> str | None:
    if is_demo_account(user):
        return None
    uid = user.get("id") if user else None
    sess = _session(uid)["youtube"]
    if sess:
        return sess
    return settings.YOUTUBE_API_KEY or None


def force_mock_for(user: dict | None) -> bool:
    """True if this user must run on mock no matter what (the demo account)."""
    return is_demo_account(user)


def gemini_for(user_id: int | None):
    """Build a GeminiService configured for this user's session (key + demo mock).
    Imported lazily to avoid a circular import at module load."""
    from ..db import repository as repo
    from ..integrations.gemini_service import GeminiService
    user = repo.get_user(user_id) if user_id is not None else None
    return GeminiService(api_key=gemini_key_for(user), force_mock=force_mock_for(user))


def status_for(user: dict | None) -> dict:
    """Non-secret summary for the settings UI (never returns the keys themselves)."""
    uid = user.get("id") if user else None
    sess = _session(uid)
    return {
        "demoAccount": is_demo_account(user),
        "geminiKeySet": bool(sess["gemini"]) and not is_demo_account(user),
        "youtubeKeySet": bool(sess["youtube"]) and not is_demo_account(user),
        "mode": "mock" if (is_demo_account(user) or not gemini_key_for(user)) else "live",
    }
