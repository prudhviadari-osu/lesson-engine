"""A tiny JSON router over http.server (standard library only).

Provides path-pattern routing with typed params, JSON parsing, an HttpError
exception for clean error responses, and bearer-token auth helpers.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..core.security import decode_access_token
from ..db import repository as repo


class HttpError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class Request:
    method: str
    path: str
    params: dict[str, str]
    query: dict[str, str]
    headers: dict[str, str]
    body: dict[str, Any] = field(default_factory=dict)
    _user: dict | None = None

    # ---- auth helpers ----
    def current_user(self) -> dict:
        if self._user is not None:
            return self._user
        auth = self.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HttpError(401, "Missing bearer token")
        payload = decode_access_token(auth.split(" ", 1)[1])
        if not payload:
            raise HttpError(401, "Invalid or expired token")
        user = repo.get_user(int(payload["sub"]))
        if not user or not user["is_active"]:
            raise HttpError(401, "User not found")
        self._user = user
        return user

    def require_roles(self, *roles: str) -> dict:
        user = self.current_user()
        if user["role"] not in roles:
            raise HttpError(403, f"Requires role(s): {', '.join(roles)}")
        return user


Handler = Callable[[Request], Any]


class Router:
    def __init__(self) -> None:
        self._routes: list[tuple[str, re.Pattern[str], Handler]] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        # Convert "/courses/{course_id}/forum" -> regex with named groups.
        regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern)
        self._routes.append((method.upper(), re.compile(f"^{regex}$"), handler))

    def get(self, pattern: str):
        return lambda fn: (self.add("GET", pattern, fn) or fn)

    def post(self, pattern: str):
        return lambda fn: (self.add("POST", pattern, fn) or fn)

    def put(self, pattern: str):
        return lambda fn: (self.add("PUT", pattern, fn) or fn)

    def match(self, method: str, path: str):
        for m, regex, handler in self._routes:
            if m != method.upper():
                continue
            match = regex.match(path)
            if match:
                return handler, match.groupdict()
        return None, None


def json_dumps(data: Any) -> bytes:
    return json.dumps(data, default=str).encode()
