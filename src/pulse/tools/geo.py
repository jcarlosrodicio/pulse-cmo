"""GEO (generative engine optimization) + link audits.

`audit_geo`   — how well the site is set up to be found + cited by AI answer
                engines (ChatGPT, Claude, Perplexity, Gemini): AI-crawler
                access in robots.txt, llms.txt, structured data, FAQ schema,
                semantic headings, answerable content.
`audit_links` — internal/external link health: counts, broken links.

Both cache a summary onto the project for the UI to render.
"""

from __future__ import annotations

import json
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from selectolax.parser import HTMLParser

from ..store import ActionStore
from .registry import Tool, tool

log = structlog.get_logger()

_UA = {"User-Agent": "Mozilla/5.0 (compatible; pulse-bot/0.1)"}

# AI answer-engine crawlers and the robots.txt user-agent token each uses
_AI_CRAWLERS = {
    "ChatGPT (OpenAI)": ["GPTBot", "OAI-SearchBot", "ChatGPT-User"],
    "Claude (Anthropic)": ["ClaudeBot", "anthropic-ai", "Claude-Web"],
    "Perplexity": ["PerplexityBot"],
    "Google AI (Gemini/AI Overviews)": ["Google-Extended"],
    "Common Crawl (training)": ["CCBot"],
}


async def _get(url: str, timeout: float = 12.0) -> tuple[int, str]:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cx:
            r = await cx.get(url, headers=_UA)
        return r.status_code, r.text
    except Exception:
        return 0, ""


def _robots_blocks(robots_text: str) -> list[tuple[list[str], list[str]]]:
    """Parse robots.txt into (user-agents, disallow-paths) blocks."""
    blocks: list[tuple[list[str], list[str]]] = []
    agents: list[str] = []
    disallows: list[str] = []
    for raw in robots_text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, val = (x.strip() for x in line.split(":", 1))
        kl = key.lower()
        if kl == "user-agent":
            if disallows and agents:
                blocks.append((agents, disallows))
                agents, disallows = [], []
            agents.append(val)
        elif kl == "disallow":
            disallows.append(val)
    if agents:
        blocks.append((agents, disallows))
    return blocks


def _crawler_blocked(robots_text: str, tokens: list[str]) -> bool:
    """True if any of the crawler's tokens is fully disallowed (Disallow: /)."""
    blocks = _robots_blocks(robots_text)
    for agents, disallows in blocks:
        for a in agents:
            if a in tokens and any(d.strip() == "/" for d in disallows):
                return True
    return False


async def _audit_geo_impl(url: str) -> dict:
    if not url.startswith("http"):
        url = "https://" + url
    status, html = await _get(url)
    if status == 0:
        return {"ok": False, "error": "could not fetch site"}

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    tree = HTMLParser(html or "")

    findings: list[dict] = []
    passed: list[dict] = []

    # robots.txt — AI crawler access
    _, robots = await _get(f"{base}/robots.txt")
    engines: list[dict] = []
    for label, tokens in _AI_CRAWLERS.items():
        blocked = _crawler_blocked(robots, tokens) if robots else False
        engines.append({"engine": label, "tokens": tokens, "blocked": blocked})
    blocked_engines = [e["engine"] for e in engines if e["blocked"]]
    if blocked_engines:
        findings.append({
            "severity": "high",
            "category": "AI crawlers",
            "description": f"robots.txt blocks: {', '.join(blocked_engines)}",
            "fix": "if you want to be cited by these engines, remove their Disallow rules",
        })
    else:
        passed.append({"check": "AI answer-engine crawlers are allowed", "category": "AI crawlers"})

    # llms.txt — emerging standard for AI-readable site summary
    llms_status, _ = await _get(f"{base}/llms.txt")
    has_llms = llms_status == 200
    if has_llms:
        passed.append({"check": "llms.txt present", "category": "llms.txt"})
    else:
        findings.append({
            "severity": "medium",
            "category": "llms.txt",
            "description": "no /llms.txt",
            "fix": "add an llms.txt summarizing your product + key pages so models ingest a clean version",
        })

    # structured data
    jsonld = tree.css("script[type='application/ld+json']")
    schema_types: set[str] = set()
    has_faq = False
    for node in jsonld:
        try:
            data = json.loads(node.text() or "{}")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict):
                t = it.get("@type")
                if isinstance(t, list):
                    schema_types.update(str(x) for x in t)
                elif t:
                    schema_types.add(str(t))
    has_faq = any("FAQ" in t or "QAPage" in t for t in schema_types)
    if jsonld:
        passed.append({"check": f"Structured data present ({', '.join(sorted(schema_types)[:4]) or 'JSON-LD'})", "category": "Schema"})
    else:
        findings.append({"severity": "high", "category": "Schema", "description": "no JSON-LD structured data", "fix": "add Organization + WebSite (and FAQPage where relevant) schema — models lean on it heavily"})
    if not has_faq:
        findings.append({"severity": "low", "category": "Schema", "description": "no FAQPage / QAPage schema", "fix": "mark up your FAQ with FAQPage schema — it's the most-cited format in AI answers"})

    # semantic headings + answerable content
    headings = tree.css("h1, h2, h3")
    question_headings = sum(1 for h in headings if "?" in (h.text() or ""))
    if len(headings) >= 4:
        passed.append({"check": f"{len(headings)} semantic headings structure the page", "category": "Structure"})
    else:
        findings.append({"severity": "medium", "category": "Structure", "description": f"only {len(headings)} headings — thin structure", "fix": "break content into clear H2/H3 sections models can quote"})
    if question_headings == 0:
        findings.append({"severity": "low", "category": "Content", "description": "no question-style headings", "fix": "add headings phrased as the questions users ask — they map directly to AI prompts"})
    else:
        passed.append({"check": f"{question_headings} question-style heading(s)", "category": "Content"})

    # meta description (models use it as a summary)
    desc = ""
    for m in tree.css("meta[name='description']"):
        desc = (m.attributes.get("content") or "").strip()
        break
    if desc:
        passed.append({"check": "Meta description present", "category": "Summary"})
    else:
        findings.append({"severity": "medium", "category": "Summary", "description": "no meta description", "fix": "add a crisp 150-char description — it's a free summary models reuse"})

    # score: weighted
    counts = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f["severity"]] += 1
    score = max(0, 100 - counts["high"] * 22 - counts["medium"] * 10 - counts["low"] * 4)

    return {
        "ok": True,
        "url": url,
        "score": score,
        "engines": engines,
        "signals": {
            "has_llms_txt": has_llms,
            "has_jsonld": bool(jsonld),
            "has_faq_schema": has_faq,
            "schema_types": sorted(schema_types),
            "heading_count": len(headings),
            "question_headings": question_headings,
            "has_meta_description": bool(desc),
        },
        "counts": counts,
        "findings": findings,
        "passed": passed,
    }


async def _audit_links_impl(url: str) -> dict:
    if not url.startswith("http"):
        url = "https://" + url
    status, html = await _get(url)
    if status == 0:
        return {"ok": False, "error": "could not fetch site"}

    parsed = urlparse(url)
    host = parsed.netloc
    tree = HTMLParser(html or "")

    internal: list[str] = []
    external: list[str] = []
    seen: set[str] = set()
    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(url, href)
        if not absolute.startswith("http"):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        if urlparse(absolute).netloc == host:
            internal.append(absolute)
        else:
            external.append(absolute)

    # HEAD-check a sample of external links for breakage (cap to keep it fast)
    sample = external[:25]
    broken: list[dict] = []
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as cx:
        for link in sample:
            try:
                r = await cx.head(link, headers=_UA)
                code = r.status_code
                if code == 405:  # some servers reject HEAD
                    r = await cx.get(link, headers=_UA)
                    code = r.status_code
            except Exception:
                code = 0
            if code == 0 or code >= 400:
                broken.append({"url": link, "status": code or "no response"})

    return {
        "ok": True,
        "url": url,
        "counts": {
            "total": len(internal) + len(external),
            "internal": len(internal),
            "external": len(external),
            "checked": len(sample),
            "broken": len(broken),
        },
        "broken": broken,
        "external_sample": external[:20],
        "internal_sample": internal[:20],
    }


def make_geo_tools(store: ActionStore | None = None, project_id: int | None = None) -> list[Tool]:
    @tool
    async def audit_geo(url: str) -> str:
        """Audit a site for AI answer-engine optimization (GEO).

        Checks whether AI crawlers (GPTBot, ClaudeBot, PerplexityBot,
        Google-Extended) are allowed in robots.txt, whether llms.txt exists,
        structured data + FAQ schema, semantic heading structure, and
        answerable content. Returns a GEO score, per-engine readiness,
        findings, and passing checks.

        Args:
            url: Full URL with https://.
        """
        result = await _audit_geo_impl(url)
        if result.get("ok") and store and project_id:
            store.set_geo_summary(project_id, result)
        return json.dumps(result, ensure_ascii=False)

    @tool
    async def audit_links(url: str) -> str:
        """Audit a page's links: internal vs external counts + broken links.

        Extracts every link on the page, classifies internal/external, and
        HEAD-checks a sample of external links for breakage.

        Args:
            url: Full URL with https://.
        """
        result = await _audit_links_impl(url)
        if result.get("ok") and store and project_id:
            store.set_links_summary(project_id, result)
        return json.dumps(result, ensure_ascii=False)

    return [audit_geo, audit_links]
