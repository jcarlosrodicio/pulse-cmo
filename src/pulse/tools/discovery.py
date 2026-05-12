"""Discovery tools — find places where the user's product is relevant.

`find_hn_opportunities` — HN Algolia API (free, no auth).
Reddit/Twitter are out for MVP per user instruction.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import structlog

from .registry import Tool, tool

log = structlog.get_logger()

HN_ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"


@tool
async def find_hn_opportunities(keywords: list[str], days_back: int = 7) -> str:
    """Search Hacker News for recent posts/comments where your product is relevant.

    Use product keywords and adjacent problem-space keywords. Returns up to
    10 recent threads with title, URL, points, and a snippet, sorted by
    recency. Read each thread to decide if it's worth a comment.

    Args:
        keywords: List of search terms (product name, problem space, competitors).
        days_back: How many days back to search (default 7, capped at 30).
    """
    if not keywords:
        return json.dumps({"ok": False, "error": "keywords list is empty"})
    days_back = max(1, min(int(days_back), 30))
    since = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())

    seen_objs: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for kw in keywords[:6]:
            params = {
                "query": kw,
                "tags": "(story,comment)",
                "numericFilters": f"created_at_i>{since}",
                "hitsPerPage": "10",
            }
            try:
                r = await client.get(HN_ALGOLIA, params=params)
                if r.status_code >= 400:
                    continue
                data = r.json()
            except Exception as e:
                log.warning("hn_search_failed", kw=kw, error=repr(e))
                continue
            for hit in data.get("hits", []):
                obj_id = hit.get("objectID") or ""
                if not obj_id or obj_id in seen_objs:
                    continue
                seen_objs[obj_id] = hit

    results = []
    for hit in seen_objs.values():
        obj_id = hit.get("objectID") or ""
        is_story = bool(hit.get("title"))
        title = hit.get("title") or hit.get("story_title") or "(comment)"
        url = (
            hit.get("url")
            or f"https://news.ycombinator.com/item?id={obj_id}"
        )
        text_blob = hit.get("story_text") or hit.get("comment_text") or ""
        text_blob = (
            text_blob.replace("<p>", "\n").replace("</p>", "").replace("<i>", "")
            .replace("</i>", "").replace("<a href=", "").strip()[:400]
        )
        results.append(
            {
                "id": obj_id,
                "kind": "story" if is_story else "comment",
                "title": title,
                "hn_url": f"https://news.ycombinator.com/item?id={obj_id}",
                "external_url": url if is_story else None,
                "points": hit.get("points"),
                "author": hit.get("author"),
                "created_at": hit.get("created_at"),
                "snippet": text_blob,
            }
        )
    results.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return json.dumps({"ok": True, "found": len(results), "items": results[:10]}, ensure_ascii=False)


def make_discovery_tools() -> list[Tool]:
    return [find_hn_opportunities]
