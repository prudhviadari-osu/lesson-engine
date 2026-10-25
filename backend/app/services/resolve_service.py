"""Resolve video + excerpt resource blocks (ported from resolve/youtube/reading.js).

Fills unresolved 'video' blocks with a real YouTube result (or a keyless
search-page fallback) and 'excerpt' blocks with a Wikipedia summary (or a
keyless search-page fallback). All stdlib (urllib) and cached for demo-safety.
Everything degrades gracefully with NO keys and NO network.
"""
from __future__ import annotations

import hashlib
import json
import logging
import urllib.parse

from ..core.config import settings
from ..db import repository as repo

logger = logging.getLogger("learnpp.resolve")

_YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"
_WIKI_SEARCH = "https://en.wikipedia.org/w/rest.php/v1/search/page"
_WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary"


def _hash(prefix: str, value: str) -> str:
    return hashlib.sha256((prefix + value).encode()).hexdigest()


def _video_fallback(q: str, reason: str) -> dict:
    return {
        "query": q, "videoId": None, "title": f'Search YouTube: "{q}"', "channel": None,
        "url": f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}",
        "embedUrl": None, "thumbnail": None, "resolved": False, "fallbackReason": reason,
    }


def find_video(query: str) -> dict | None:
    q = (query or "").strip()
    if not q:
        return None
    hashed = _hash("yt:", q)
    cached = repo.cache_get("youtube", hashed)
    if cached is not None:
        return {**cached, "cached": True}

    key = settings.YOUTUBE_API_KEY
    if not key or settings.USE_MOCK_INTEGRATIONS:
        return _video_fallback(q, "no_api_key")

    import urllib.request  # pragma: no cover - network path
    url = (  # pragma: no cover
        f"{_YT_SEARCH}?part=snippet&type=video&videoEmbeddable=true&safeSearch=moderate"
        f"&maxResults=3&q={urllib.parse.quote(q)}&key={key}"
    )
    try:  # pragma: no cover - network path
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        item = (data.get("items") or [None])[0]
        if not item:
            return _video_fallback(q, "no_results")
        vid = item["id"]["videoId"]
        video = {
            "query": q, "videoId": vid, "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "url": f"https://www.youtube.com/watch?v={vid}",
            "embedUrl": f"https://www.youtube.com/embed/{vid}",
            "thumbnail": (item["snippet"].get("thumbnails", {}).get("medium") or {}).get("url"),
            "resolved": True,
        }
        repo.cache_set("youtube", hashed, video)
        return {**video, "cached": False}
    except Exception as exc:  # pragma: no cover
        logger.warning("YouTube lookup failed (%s)", exc)
        return _video_fallback(q, "fetch_error")


def _reading_fallback(topic: str, reason: str) -> dict:
    return {
        "source": "none", "topic": topic, "heading": None, "text": "",
        "url": f"https://en.wikipedia.org/wiki/Special:Search?search={urllib.parse.quote(topic)}",
        "attachmentId": None, "page": None, "resolved": False, "fallbackReason": reason,
    }


def find_reading(topic: str) -> dict | None:
    t = (topic or "").strip()
    if not t:
        return None
    hashed = _hash("wiki:", t)
    cached = repo.cache_get("wikipedia", hashed)
    if cached is not None:
        return {**cached, "cached": True}

    if settings.USE_MOCK_INTEGRATIONS:
        return _reading_fallback(t, "offline_mock")

    import urllib.request  # pragma: no cover - network path
    headers = {"User-Agent": "learning++/1.0 (hackathon project)"}
    try:  # pragma: no cover - network path
        sreq = urllib.request.Request(
            f"{_WIKI_SEARCH}?q={urllib.parse.quote(t)}&limit=1", headers=headers
        )
        with urllib.request.urlopen(sreq, timeout=20) as resp:
            sdata = json.loads(resp.read().decode())
        page = (sdata.get("pages") or [None])[0]
        if not page:
            return _reading_fallback(t, "wiki_no_page")
        kreq = urllib.request.Request(
            f"{_WIKI_SUMMARY}/{urllib.parse.quote(page['key'])}", headers=headers
        )
        with urllib.request.urlopen(kreq, timeout=20) as resp:
            sdoc = json.loads(resp.read().decode())
        excerpt = {
            "source": "wikipedia", "topic": t, "heading": sdoc.get("title"),
            "text": sdoc.get("extract", ""),
            "url": (sdoc.get("content_urls", {}).get("desktop", {}) or {}).get("page"),
            "attachmentId": None, "page": None, "resolved": bool(sdoc.get("extract")),
        }
        repo.cache_set("wikipedia", hashed, excerpt)
        return {**excerpt, "cached": False}
    except Exception as exc:  # pragma: no cover
        logger.warning("Wikipedia lookup failed (%s)", exc)
        return _reading_fallback(t, "wiki_error")


def resolve_resources(assignment_id: int) -> dict:
    """Resolve all unresolved video + excerpt blocks for an assignment."""
    blocks = repo.list_resource_blocks(assignment_id, ("video", "excerpt"))
    resolved_videos = resolved_readings = skipped = 0
    for b in blocks:
        payload = json.loads(b["payload_json"])
        if payload.get("resolved") is True:
            skipped += 1
            continue
        if b["type"] == "video":
            v = find_video(payload.get("query"))
            if v:
                repo.update_lesson_block_payload(b["id"], json.dumps({**payload, **v}))
                if v.get("resolved"):
                    resolved_videos += 1
        else:
            r = find_reading(payload.get("topic"))
            if r:
                repo.update_lesson_block_payload(b["id"], json.dumps({**payload, **r}))
                if r.get("resolved"):
                    resolved_readings += 1
    return {
        "assignmentId": assignment_id, "resolvedVideos": resolved_videos,
        "resolvedReadings": resolved_readings, "skipped": skipped,
        "totalResourceBlocks": len(blocks),
    }
