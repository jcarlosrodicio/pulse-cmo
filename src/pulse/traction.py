"""Traction scan — map a company's digital footprint.

Searches the web + Reddit + Hacker News for the product name / URL, classifies
every mention by platform, and runs one LLM synthesis pass to assess where the
company is strong, the sentiment, and what to focus on next. The result is the
project's "digital fingerprint" — stored on the project as `traction_summary`.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from .config import Config
from .llm import LLM, Message

log = structlog.get_logger()

HN_ALGOLIA = "https://hn.algolia.com/api/v1/search"

REDDIT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
REDDIT_HOSTS = ["https://old.reddit.com", "https://api.reddit.com"]


# ---------------------------------------------------------------------------
# Platform classification from a URL host.
# ---------------------------------------------------------------------------

_PLATFORM_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"reddit\.com"), "reddit", "Reddit"),
    (re.compile(r"news\.ycombinator\.com|ycombinator"), "hn", "Hacker News"),
    (re.compile(r"(twitter|x)\.com"), "x", "X / Twitter"),
    (re.compile(r"github\.com"), "github", "GitHub"),
    (re.compile(r"youtube\.com|youtu\.be"), "youtube", "YouTube"),
    (re.compile(r"producthunt\.com"), "producthunt", "Product Hunt"),
    (re.compile(r"linkedin\.com"), "linkedin", "LinkedIn"),
    (re.compile(r"medium\.com|dev\.to|substack\.com|hashnode"), "blog", "Blogs"),
    (re.compile(r"g2\.com|capterra|alternativeto|theresanaiforthat|futurepedia|"
                r"producthunt|saashub|slant\.co|toolify"), "directory", "Directories"),
]


def _classify(url: str) -> tuple[str, str]:
    host = (urlparse(url).hostname or "").lower()
    for pat, key, label in _PLATFORM_RULES:
        if pat.search(host):
            return key, label
    return "web", "Web & News"


# ---------------------------------------------------------------------------
# Raw collectors.
# ---------------------------------------------------------------------------

def _parse_web_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("results") or data.get("data") or data.get("items") or []
    if isinstance(items, dict):
        items = items.get("items") or items.get("results") or []
    out = []
    for it in items or []:
        url = it.get("url") or it.get("link") or ""
        if not url:
            continue
        out.append({
            "title": (it.get("title") or it.get("name") or "").strip(),
            "url": url,
            "snippet": (it.get("snippet") or it.get("description") or it.get("content") or "").strip().replace("\n", " ")[:280],
            "date": it.get("date") or it.get("published") or it.get("published_at") or "",
        })
    return out


async def _web_search(base_url: str, api_key: str, query: str, n: int = 8) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as cx:
            r = await cx.post(
                f"{base_url.rstrip('/')}/v1/tools/search",
                headers=headers,
                json={"query": query, "num_results": n},
            )
        if r.status_code >= 400:
            return []
        return _parse_web_items(r.json())
    except Exception as e:
        log.warning("traction_web_search_failed", query=query, error=repr(e))
        return []


async def _reddit_search(query: str, n: int = 12) -> list[dict[str, Any]]:
    params = {"q": query, "sort": "relevance", "limit": str(n), "t": "year"}
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as cx:
        for host in REDDIT_HOSTS:
            try:
                r = await cx.get(f"{host}/search.json", headers=REDDIT_HEADERS, params=params)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            try:
                data = r.json()
            except Exception:
                continue
            out = []
            for c in (data.get("data") or {}).get("children") or []:
                p = c.get("data", {})
                out.append({
                    "title": p.get("title") or "",
                    "url": f"https://www.reddit.com{p.get('permalink', '')}",
                    "snippet": (p.get("selftext") or "")[:280],
                    "date": _ts_to_iso(p.get("created_utc")),
                    "extra": f"r/{p.get('subreddit')} · {p.get('score', 0)} pts · {p.get('num_comments', 0)} comments",
                })
            return out
    return []


async def _hn_search(query: str, n: int = 12) -> list[dict[str, Any]]:
    params = {"query": query, "tags": "(story,comment)", "hitsPerPage": str(n)}
    try:
        async with httpx.AsyncClient(timeout=15.0) as cx:
            r = await cx.get(HN_ALGOLIA, params=params)
        if r.status_code >= 400:
            return []
        data = r.json()
    except Exception as e:
        log.warning("traction_hn_failed", error=repr(e))
        return []
    out = []
    for hit in data.get("hits", []):
        obj = hit.get("objectID") or ""
        title = hit.get("title") or hit.get("story_title") or "(comment)"
        text = (hit.get("story_text") or hit.get("comment_text") or "")
        text = re.sub(r"<[^>]+>", "", text).strip()[:280]
        out.append({
            "title": title,
            "url": f"https://news.ycombinator.com/item?id={obj}",
            "snippet": text,
            "date": hit.get("created_at") or "",
            "extra": f"{hit.get('points') or 0} pts",
        })
    return out


def _ts_to_iso(ts: float | None) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Synthesis.
# ---------------------------------------------------------------------------

_SYNTH_PROMPT = """\
You analyze a company's digital footprint — every place it's mentioned online —
and tell the founder where they're strong and where to focus.

You're given the product and a list of mentions grouped by platform. Output
STRICT JSON only, no preface, no fences:

{
  "strongest": "<platform key with the most meaningful presence>",
  "sentiment": { "positive": <int>, "neutral": <int>, "negative": <int> },
  "platforms": {
    "<platform key>": { "strength": "strong|emerging|thin|none", "summary": "<1-2 sentences: what's being said + how strong>" }
  },
  "insights": [ "<3-5 specific, actionable observations — where to double down, where there's a gap, what's working>" ]
}

Rules:
- strength: 'strong' = active, positive, recurring presence; 'emerging' = a few
  real mentions; 'thin' = barely there; 'none' = no real presence.
- sentiment counts should sum to roughly the number of mentions you assessed.
- insights are the payload — be concrete. "You're strongest on Reddit in
  r/LocalLLaMA; lean in there" beats "engage your community". Call out gaps
  (e.g. "no Hacker News presence — a Show HN could land").
- Output ONLY the JSON object. First character is '{'.\
"""


def _parse_json(raw: str) -> Any | None:
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    m = re.search(r"\{.*\}|\[.*\]", s, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


async def scan_traction(
    *, config: Config, llm: LLM, store: Any, project_id: int
) -> dict[str, Any]:
    """Run the full footprint scan and persist it on the project."""
    project = store.get_project(project_id)
    if not project:
        raise ValueError(f"project {project_id} not found")

    name = (project.get("name") or "").strip()
    url = project.get("url") or ""
    host = (urlparse(url).hostname or "").replace("www.", "")
    bare = host.split(".")[0] if host else name

    # query terms: name, host, and name+context combos
    terms = list(dict.fromkeys([t for t in [name, host, bare] if t]))

    base_url = config.web.base_url
    try:
        api_key = config.web_api_key()
    except Exception:
        api_key = ""

    # ---- fan out searches ----
    tasks: list = []
    if api_key:
        for q in [name, f'"{name}" review', f"{name} alternative", f"{name} vs", host]:
            if q.strip():
                tasks.append(_web_search(base_url, api_key, q, 8))
    for q in terms[:2]:
        tasks.append(_reddit_search(q, 12))
        tasks.append(_hn_search(q, 12))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # ---- dedupe + classify ----
    seen: dict[str, dict[str, Any]] = {}
    for batch in results:
        if isinstance(batch, Exception):
            continue
        for item in batch:
            u = item.get("url")
            if not u or u in seen:
                continue
            # skip the company's own site — that's not "traction", it's home
            ihost = (urlparse(u).hostname or "").replace("www.", "")
            if host and ihost == host:
                continue
            key, label = _classify(u)
            item["platform"] = key
            item["platform_label"] = label
            seen[u] = item

    mentions = list(seen.values())

    # group by platform
    groups: dict[str, dict[str, Any]] = {}
    for m in mentions:
        g = groups.setdefault(m["platform"], {"key": m["platform"], "label": m["platform_label"], "mentions": []})
        g["mentions"].append(m)
    for g in groups.values():
        g["count"] = len(g["mentions"])
        g["mentions"].sort(key=lambda x: x.get("date") or "", reverse=True)

    # ---- synthesis ----
    synth: dict[str, Any] = {}
    if mentions:
        payload = {
            k: [{"title": x["title"], "snippet": x["snippet"], "extra": x.get("extra", "")} for x in g["mentions"][:8]]
            for k, g in groups.items()
        }
        user = (
            f"PRODUCT: {name} ({url})\n"
            f"WHAT IT DOES: {project.get('description') or '(unknown)'}\n\n"
            f"MENTIONS BY PLATFORM:\n{json.dumps(payload, ensure_ascii=False)[:6000]}\n\n"
            "Analyze the footprint. Output only the JSON object."
        )
        try:
            raw = await llm.complete(
                [Message(role="system", content=_SYNTH_PROMPT), Message(role="user", content=user)],
                temperature=0.4,
                max_tokens=1200,
            )
            synth = _parse_json(raw) or {}
        except Exception as e:
            log.warning("traction_synth_failed", error=repr(e))

    # merge synthesis into the platform groups
    synth_platforms = synth.get("platforms") or {}
    platform_list = []
    for k, g in sorted(groups.items(), key=lambda kv: -kv[1]["count"]):
        meta = synth_platforms.get(k) or {}
        platform_list.append({
            "key": k,
            "label": g["label"],
            "count": g["count"],
            "strength": meta.get("strength") or ("emerging" if g["count"] >= 2 else "thin"),
            "summary": meta.get("summary") or "",
            "mentions": g["mentions"][:10],
        })

    summary = {
        "status": "done",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "query_terms": terms,
        "totals": {"mentions": len(mentions), "platforms": len(groups)},
        "strongest": synth.get("strongest") or (platform_list[0]["key"] if platform_list else None),
        "sentiment": synth.get("sentiment") or {},
        "insights": synth.get("insights") or _fallback_insights(platform_list),
        "platforms": platform_list,
    }
    store.set_traction_summary(project_id, summary)
    log.info("traction_scan_done", project_id=project_id, mentions=len(mentions), platforms=len(groups))
    return summary


def _fallback_insights(platforms: list[dict[str, Any]]) -> list[str]:
    if not platforms:
        return ["No external mentions found yet. You're early — every channel is greenfield."]
    top = platforms[0]
    out = [f"Most of your footprint is on {top['label']} ({top['count']} mentions) — that's your warmest audience."]
    have = {p["key"] for p in platforms}
    if "hn" not in have:
        out.append("No Hacker News presence yet — a Show HN could open a new audience.")
    if "reddit" not in have:
        out.append("No Reddit footprint — find the subreddits your users live in.")
    return out
