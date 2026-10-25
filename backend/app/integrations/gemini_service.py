"""Gemini-backed AI services with offline mock fallbacks.

On the Ubuntu VM (with internet + GEMINI_API_KEY set) this calls the real
Gemini REST API over urllib (zero third-party deps). In the offline sandbox
everything falls back to deterministic mocks so the whole app stays runnable
with NO key.

Two low-level helpers mirror the JS lesson engine's gemini.js:
  * generate_json  — structured output (responseMimeType=application/json),
                     precise/low temperature, cached by input hash.
  * generate_text  — free-text conversational turn (warm temperature, system
                     instruction, multi-turn history), NOT cached.
Both try the primary model, then fall back to lighter models on overload
(503) / rate-limit (429) with a short backoff, exactly like the JS engine.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from ..core.config import settings
from ..db import repository as repo

logger = logging.getLogger("learnpp.gemini")

_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

_MAX_RETRIES = 3


class NoApiKey(Exception):
    code = "NO_API_KEY"


class Overloaded(Exception):
    code = "OVERLOADED"


def _model_chain() -> list[str]:
    primary = settings.GEMINI_MODEL
    fallbacks = [m.strip() for m in settings.GEMINI_FALLBACKS.split(",") if m.strip()]
    chain = [primary] + [m for m in fallbacks if m != primary]
    return chain


def _is_transient(exc: Exception) -> bool:
    status = getattr(exc, "code", None)
    msg = str(exc).lower()
    return (
        status in (500, 503, 429)
        or "overload" in msg or "high demand" in msg
        or "unavailable" in msg or "rate" in msg or "quota" in msg
        or "resource_exhausted" in msg
    )


def _hash_request(parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _call_with_fallback(payload: dict) -> tuple[dict, str]:
    """Try each model in the chain; retry transient errors with backoff."""
    import urllib.error
    import urllib.request

    key = settings.GEMINI_API_KEY
    if not key:
        raise NoApiKey("GEMINI_API_KEY is not set.")

    last_err: Exception | None = None
    for model in _model_chain():
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                url = _GENERATE_URL.format(model=model, key=key)
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode()), model
            except urllib.error.HTTPError as exc:  # pragma: no cover - network path
                exc.code = exc.code  # keep status for _is_transient
                last_err = exc
                if _is_transient(exc) and attempt < _MAX_RETRIES:
                    time.sleep(attempt * 1.5)
                    continue
                if _is_transient(exc):
                    break  # next model
                raise
            except Exception as exc:  # pragma: no cover - network path
                last_err = exc
                if _is_transient(exc) and attempt < _MAX_RETRIES:
                    time.sleep(attempt * 1.5)
                    continue
                if _is_transient(exc):
                    break
                raise
    raise Overloaded(
        f"All Gemini models overloaded/unavailable (tried: {', '.join(_model_chain())})."
    )


def _extract_text(data: dict) -> str:
    return data["candidates"][0]["content"]["parts"][0]["text"]

class GeminiService:
    """Low-level Gemini access (ported from the JS gemini.js)."""

    def __init__(self) -> None:
        self.use_mock = settings.USE_MOCK_INTEGRATIONS or not settings.GEMINI_API_KEY

    # -- structured JSON (decompose) ---------------------------------------
    def generate_json(self, *, prompt: str, cache_key_extra: str = "") -> dict[str, Any]:
        """Return parsed JSON from Gemini (responseMimeType=application/json).

        Cached by input hash for demo-safety. The response must be a JSON
        object/array; the caller validates the shape.
        """
        request_hash = _hash_request(
            {"model": settings.GEMINI_MODEL, "prompt": prompt, "extra": cache_key_extra}
        )
        cached = repo.cache_get("gemini", request_hash)
        if cached is not None:
            return {"data": cached, "cached": True, "model_used": "cache"}

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        data, model_used = _call_with_fallback(payload)  # pragma: no cover - network
        parsed = json.loads(_extract_text(data))  # pragma: no cover - network
        repo.cache_set("gemini", request_hash, parsed)  # pragma: no cover - network
        return {"data": parsed, "cached": False, "model_used": model_used}  # pragma: no cover

    # -- free-text chat (tutor / feedback) ---------------------------------
    def generate_text(
        self,
        *,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        history: list[dict] | None = None,
    ) -> dict[str, Any]:
        """A conversational turn. NOT cached — every reply is live.

        history items: {"role": "user"|"model", "text": str}. Raises NoApiKey
        when no key is set so callers can route a mock or a graceful error.
        """
        if temperature is None:
            temperature = settings.TUTOR_TEMPERATURE
        contents: list[dict] = []
        for turn in history or []:
            role = "model" if turn.get("role") == "model" else "user"
            contents.append({"role": role, "parts": [{"text": str(turn.get("text", ""))}]})
        contents.append({"role": "user", "parts": [{"text": str(prompt)}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system and system.strip():
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        data, model_used = _call_with_fallback(payload)  # pragma: no cover - network
        return {"text": _extract_text(data), "model_used": model_used}  # pragma: no cover
