"""Learn++ server entrypoint (standard library http.server).

Serves the JSON API under /api and the static frontend at the root so the
whole tool runs on a single localhost origin (per the PRD's localhost UI).

Run:  python -m backend.app.main
"""
from __future__ import annotations

import json
import logging
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core.config import settings
from .db.database import init_db
from .web.framework import HttpError, Request, json_dumps
from .web.routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("learnpp.server")

# backend/app/main.py -> parents[2] == repo root (…/sandbox) -> frontend/
_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class Handler(BaseHTTPRequestHandler):
    server_version = "LearnPP/0.1"

    def log_message(self, fmt: str, *args) -> None:  # quieter logging
        logger.info("%s - %s", self.address_string(), fmt % args)

    # -- helpers ------------------------------------------------------------
    def _send_json(self, status: int, payload) -> None:
        data = json_dumps(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            raise HttpError(400, "Request body must be valid JSON")

    def _serve_static(self, path: str) -> None:
        if not _FRONTEND_DIR.exists():
            self._send_json(404, {"detail": "Frontend not built"})
            return
        rel = path.lstrip("/") or "index.html"
        candidate = (_FRONTEND_DIR / rel).resolve()
        # Prevent path traversal outside the frontend dir.
        if _FRONTEND_DIR.resolve() not in candidate.parents and candidate != _FRONTEND_DIR.resolve():
            candidate = _FRONTEND_DIR / "index.html"
        if not candidate.is_file():
            candidate = _FRONTEND_DIR / "index.html"  # SPA fallback
        ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- dispatch -----------------------------------------------------------
    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api"):
            if method == "GET":
                self._serve_static(path)
            else:
                self._send_json(404, {"detail": "Not found"})
            return

        handler, params = router.match(method, path)
        if handler is None:
            self._send_json(404, {"detail": f"No route for {method} {path}"})
            return

        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        headers = {k.lower(): v for k, v in self.headers.items()}
        try:
            body = self._read_body() if method in {"POST", "PUT"} else {}
            req = Request(method, path, params or {}, query, headers, body)
            result = handler(req)
            status = 200
            if isinstance(result, dict) and "status" in result and isinstance(result["status"], int):
                status = result.pop("status")
            self._send_json(status, result)
        except HttpError as exc:
            self._send_json(exc.status, {"detail": exc.detail})
        except Exception as exc:  # pragma: no cover
            logger.exception("Unhandled error")
            self._send_json(500, {"detail": f"Internal error: {exc}"})

    def do_OPTIONS(self) -> None:
        self._send_json(204, {})

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")


def main() -> None:
    init_db()
    addr = (settings.HOST, settings.PORT)
    httpd = ThreadingHTTPServer(addr, Handler)
    logger.info("Learn++ running on http://%s:%d  (mock=%s)",
                settings.HOST, settings.PORT, settings.USE_MOCK_INTEGRATIONS)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
