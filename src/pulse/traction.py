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
from .entity_resolution import build_entity_profile, deterministic_entity_check, resolve_ambiguous
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


def _classify(url: str, source: str = "") -> tuple[str, str]:
    if source == "news":
        return "news", "News"
    host = (urlparse(url).hostname or "").lower()
    for pat, key, label in _PLATFORM_RULES:
        if pat.search(host):
            return key, label
    return "web", "Web"


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


async def _web_search(
    base_url: str,
    api_key: str,
    query: str,
    n: int = 8,
    *,
    path: str = "/v1/tools/search",
    source: str = "web",
) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as cx:
            r = await cx.post(
                f"{base_url.rstrip('/')}{path}",
                headers=headers,
                json={"query": query, "num_results": n},
            )
        if r.status_code >= 400:
            return []
        items = _parse_web_items(r.json())
        for item in items:
            item["source"] = source
        return items
    except Exception as e:
        log.warning("traction_web_search_failed", query=query, error=repr(e))
        return []


async def _news_search(base_url: str, api_key: str, query: str, n: int = 8) -> list[dict[str, Any]]:
    return await _web_search(
        base_url,
        api_key,
        query,
        n,
        path="/v1/tools/search/news",
        source="news",
    )


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
                    "source": "reddit",
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
            "source": "hn",
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
    from .text import parse_json_lenient

    return parse_json_lenient(raw)


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
    identity = build_entity_profile(project, store.get_product_brain(project_id))

    # Brand discovery stays broad, but the primary queries carry the product
    # category or a verified identifier. The bare name remains as a candidate
    # source and is filtered by entity resolution below.
    query_terms: list[str] = []

    def add_query(q: str) -> None:
        q = (q or "").strip()
        if q and q.lower() not in {x.lower() for x in query_terms}:
            query_terms.append(q)

    for phrase in ("expense tracker", "personal finance", "control de gastos", "expenses"):
        add_query(f'"{name}" "{phrase}"')
    for identifier in identity.get("strong_identifiers") or []:
        add_query(identifier)
    if host:
        add_query(host)
    add_query(f'"{name}" review')
    add_query(name)

    base_url = config.web.base_url
    try:
        api_key = config.web_api_key()
    except Exception:
        api_key = ""

    # ---- fan out searches ----
    tasks: list[tuple[str, Any]] = []
    if api_key:
        for q in query_terms[:8]:
            tasks.append(("web", _web_search(base_url, api_key, q, 8)))
        for q in query_terms[:4]:
            tasks.append(("news", _news_search(base_url, api_key, q, 8)))
    for q in query_terms[:4]:
        tasks.append(("reddit", _reddit_search(q, 12)))
        tasks.append(("hn", _hn_search(q, 12)))

    results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)

    # ---- dedupe + classify ----
    seen: dict[str, dict[str, Any]] = {}
    for (source, _), batch in zip(tasks, results):
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
            item["source"] = item.get("source") or source
            key, label = _classify(u, item["source"])
            item["platform"] = key
            item["platform_label"] = label
            item["id"] = u
            seen[u] = item

    candidates = list(seen.values())
    accepted: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in candidates:
        verdict = deterministic_entity_check(item, identity)
        item.update(
            entity_decision=verdict["decision"],
            entity=verdict["entity"],
            entity_confidence=verdict["confidence"],
            entity_match_reason=verdict["reason"],
        )
        if verdict["decision"] == "accept":
            accepted.append(item)
        elif verdict["decision"] == "ambiguous":
            ambiguous.append(item)
        else:
            rejected.append(item)

    if ambiguous and identity.get("name", "").strip().lower() == "tally":
        # Tally has several unrelated products with the same name and even
        # the same category. Without an exact official identifier, retain the
        # candidate as uncertain rather than asking the model to guess.
        for item in ambiguous:
            item.update(
                entity_decision="uncertain",
                entity="unknown",
                entity_confidence=0.45,
                entity_match_reason="shared Tally name without an exact official identifier or domain",
            )
    elif ambiguous:
        verdicts = await resolve_ambiguous(
            llm,
            profile=identity,
            items=ambiguous,
            source="traction brand mentions",
        )
        for item in ambiguous:
            verdict = verdicts.get(item["id"], {
                "decision": "uncertain",
                "entity": "unknown",
                "confidence": 0.4,
                "reason": "no entity verdict",
            })
            item.update(
                entity_decision=verdict["decision"],
                entity=verdict["entity"],
                entity_confidence=verdict["confidence"],
                entity_match_reason=verdict["reason"],
            )
            if verdict["decision"] == "accept":
                accepted.append(item)
            elif verdict["decision"] == "reject":
                rejected.append(item)

    mentions = accepted

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
            "ENTITY RULE: these are already resolved mentions of this exact product; "
            "do not merge them with same-name products or generic uses of the word.\n"
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
        "query_terms": query_terms,
        "totals": {
            "mentions": len(mentions),
            "platforms": len(groups),
            "candidates": len(candidates),
            "accepted": len(mentions),
            "rejected": len(rejected),
            "uncertain": sum(1 for item in ambiguous if item.get("entity_decision") == "uncertain"),
        },
        "strongest": synth.get("strongest") or (platform_list[0]["key"] if platform_list else None),
        "sentiment": synth.get("sentiment") or {},
        "insights": synth.get("insights") or _fallback_insights(platform_list),
        "platforms": platform_list,
        "entity_resolution": {
            "profile": identity,
            "rejected": [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("snippet", ""),
                    "source": item.get("source", ""),
                    "entity": item.get("entity", "unknown"),
                    "confidence": item.get("entity_confidence", 0.0),
                    "reason": item.get("entity_match_reason", ""),
                }
                for item in rejected[:30]
            ],
            "uncertain": [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("snippet", ""),
                    "source": item.get("source", ""),
                    "confidence": item.get("entity_confidence", 0.0),
                    "reason": item.get("entity_match_reason", ""),
                }
                for item in ambiguous if item.get("entity_decision") == "uncertain"
            ][:30],
        },
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
