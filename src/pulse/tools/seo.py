"""SEO audit tools.

`audit_seo` does cheap structural checks (meta tags, h1, robots, sitemap).
`check_pagespeed` hits Google PageSpeed Insights (free, API key optional).

Both side-effect a summary to the project so the UI can render scores
without re-running the tool.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

import httpx
import structlog
from selectolax.parser import HTMLParser

from ..store import ActionStore
from .registry import Tool, tool

log = structlog.get_logger()

PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# --- shared HTML structural audit ------------------------------------------


async def _fetch_html(url: str) -> tuple[int, str, dict[str, str]]:
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": "pulse-bot/0.1"})
    return r.status_code, r.text, dict(r.headers)


async def _fetch_text(url: str) -> tuple[int, str]:
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "pulse-bot/0.1"})
        return r.status_code, r.text
    except Exception:
        return 0, ""


async def _audit_seo_impl(url: str) -> dict:
    if not url.startswith("http"):
        url = "https://" + url
    try:
        status, html, headers = await _fetch_html(url)
    except Exception as e:
        return {"ok": False, "error": f"could not fetch: {e}"}

    if status >= 400:
        return {"ok": False, "error": f"{url} returned {status}"}

    findings: list[dict] = []
    passed: list[dict] = []
    tree = HTMLParser(html)

    title = tree.css_first("title")
    title_text = title.text().strip() if title and title.text() else ""
    if not title_text:
        findings.append({"severity": "high", "category": "Meta Title", "description": "missing <title> tag", "fix": "add a 50-60 char title tag that includes your primary keyword"})
    elif len(title_text) > 70:
        findings.append({"severity": "low", "category": "Meta Title", "description": f"title is {len(title_text)} chars (>70 will truncate in SERPs)", "fix": "shorten title to 50-60 chars"})
    elif len(title_text) < 20:
        findings.append({"severity": "medium", "category": "Meta Title", "description": f"title is {len(title_text)} chars (very short)", "fix": "expand to 50-60 chars with primary keyword"})
    else:
        passed.append({"check": "Title tag length is optimal", "category": "Meta Title"})

    desc = None
    for m in tree.css("meta[name='description']"):
        desc = m.attributes.get("content") or ""
        break
    if not desc:
        findings.append({"severity": "high", "category": "Meta Description", "description": "missing meta description", "fix": "add a 140-160 char meta description summarizing the page"})
    elif len(desc) < 70:
        findings.append({"severity": "low", "category": "Meta Description", "description": f"meta description is {len(desc)} chars (short)", "fix": "expand to ~150 chars"})
    elif len(desc) > 160:
        findings.append({"severity": "medium", "category": "Meta Description", "description": f"meta description is {len(desc)} chars (exceeds Google's ~155 limit)", "fix": "trim to under 155 chars without losing the value prop"})
    else:
        passed.append({"check": "Meta description present and optimal", "category": "Meta Description"})

    h1s = tree.css("h1")
    if not h1s:
        findings.append({"severity": "high", "category": "H1 Heading", "description": "no <h1> on the page", "fix": "add a single h1 with your main keyword"})
    elif len(h1s) > 1:
        findings.append({"severity": "low", "category": "H1 Heading", "description": f"{len(h1s)} <h1> tags (should be 1)", "fix": "promote one to h1, downgrade the rest to h2/h3"})
    else:
        passed.append({"check": "Single H1 tag present", "category": "H1 Heading"})

    og_tags = {t.attributes.get("property"): (t.attributes.get("content") or "").strip() for t in tree.css("meta[property^='og:']")}
    missing_og = [k for k in ("og:title", "og:description", "og:image") if not og_tags.get(k)]
    if missing_og:
        findings.append({"severity": "medium", "category": "Open Graph", "description": f"missing OG tags: {', '.join(missing_og)}", "fix": "add open graph tags for better social previews"})
    else:
        passed.append({"check": "Open Graph tags present", "category": "Open Graph"})

    imgs = tree.css("img")
    missing_alt = sum(1 for i in imgs if not (i.attributes.get("alt") or "").strip())
    if missing_alt > 0:
        findings.append({"severity": "medium" if missing_alt > 3 else "low", "category": "Accessibility", "description": f"{missing_alt} of {len(imgs)} images missing alt text", "fix": "add descriptive alt='...' to every content image"})

    has_jsonld = bool(tree.css("script[type='application/ld+json']"))
    if not has_jsonld:
        findings.append({"severity": "medium", "category": "Schema", "description": "no JSON-LD structured data", "fix": "add Organization + WebSite schema for richer SERP results"})
    else:
        passed.append({"check": "Structured data (JSON-LD) present", "category": "Schema"})

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_status, robots_text = await _fetch_text(f"{base}/robots.txt")
    if robots_status != 200 or not robots_text.strip():
        findings.append({"severity": "low", "category": "Crawl", "description": "no robots.txt found", "fix": "add robots.txt that references your sitemap.xml"})
    else:
        passed.append({"check": "robots.txt is served", "category": "Crawl"})
        if "sitemap" not in robots_text.lower():
            findings.append({"severity": "low", "category": "Crawl", "description": "robots.txt does not reference sitemap", "fix": "add 'Sitemap: <full sitemap.xml URL>' line"})

    sitemap_status, sitemap_text = await _fetch_text(f"{base}/sitemap.xml")
    has_sitemap = sitemap_status == 200 and "<loc>" in sitemap_text
    if not has_sitemap:
        findings.append({"severity": "medium", "category": "Crawl", "description": "no sitemap.xml at /sitemap.xml", "fix": "generate and serve a sitemap.xml listing all canonical URLs"})
    else:
        passed.append({"check": "Sitemap.xml is served", "category": "Crawl"})

    canonical = tree.css_first("link[rel='canonical']")
    if not canonical:
        findings.append({"severity": "low", "category": "Canonical", "description": "no canonical link tag", "fix": "add <link rel='canonical' href='<url>'> to avoid duplicate-content issues"})
    else:
        passed.append({"check": "Canonical tag present", "category": "Canonical"})

    if url.startswith("https://"):
        passed.append({"check": "HTTPS enabled", "category": "Security"})

    headers_lower = {k.lower(): v for k, v in headers.items()}
    if headers_lower.get("strict-transport-security"):
        passed.append({"check": "HSTS header present", "category": "Security"})

    counts = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f["severity"]] += 1
    score = max(0, 100 - counts["high"] * 20 - counts["medium"] * 8 - counts["low"] * 3)

    return {
        "ok": True,
        "url": url,
        "score": score,
        "summary": {
            "title": title_text[:120],
            "description": (desc or "")[:200],
            "h1_count": len(h1s),
            "img_count": len(imgs),
            "missing_alts": missing_alt,
            "has_sitemap": has_sitemap,
            "has_jsonld": has_jsonld,
        },
        "counts": counts,
        "findings": findings,
        "passed": passed,
    }


async def _pagespeed_impl(url: str, strategy: str = "mobile") -> dict:
    if strategy not in ("mobile", "desktop"):
        strategy = "mobile"
    if not url.startswith("http"):
        url = "https://" + url

    params = {
        "url": url,
        "strategy": strategy,
        "category": ["performance", "accessibility", "seo", "best-practices"],
    }
    key = os.getenv("PAGESPEED_API_KEY")
    if key:
        params["key"] = key

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(PAGESPEED_URL, params=params)
    except Exception as e:
        return {"ok": False, "error": f"pagespeed fetch failed: {e}"}

    if r.status_code >= 400:
        return {"ok": False, "error": f"pagespeed returned {r.status_code}"}

    data = r.json()
    lr = data.get("lighthouseResult") or {}
    cats = lr.get("categories") or {}
    audits = lr.get("audits") or {}

    def score_of(cat: str) -> int | None:
        c = cats.get(cat)
        if not c:
            return None
        s = c.get("score")
        return int(s * 100) if s is not None else None

    def metric(audit_id: str) -> dict | None:
        a = audits.get(audit_id)
        if not a:
            return None
        return {
            "display_value": a.get("displayValue"),
            "numeric_value": a.get("numericValue"),
            "score": a.get("score"),
        }

    opportunities: list[dict] = []
    for key, a in audits.items():
        if not a:
            continue
        score = a.get("score")
        if score is None or score >= 0.9:
            continue
        title = a.get("title", "")
        if not title:
            continue
        impact = a.get("details", {}).get("overallSavingsMs") or 0
        opportunities.append(
            {
                "id": key,
                "title": title,
                "description": re.sub(r"\[Learn more.*?\]\(.*?\)", "", a.get("description", "")).strip()[:300],
                "score": int(score * 100) if isinstance(score, (int, float)) else None,
                "savings_ms": int(impact) if impact else None,
            }
        )
    opportunities.sort(key=lambda x: -(x.get("savings_ms") or 0))

    return {
        "ok": True,
        "url": url,
        "strategy": strategy,
        "scores": {
            "performance": score_of("performance"),
            "accessibility": score_of("accessibility"),
            "seo": score_of("seo"),
            "best_practices": score_of("best-practices"),
        },
        "core_web_vitals": {
            "lcp": metric("largest-contentful-paint"),
            "fcp": metric("first-contentful-paint"),
            "cls": metric("cumulative-layout-shift"),
            "tbt": metric("total-blocking-time"),
            "si": metric("speed-index"),
        },
        "opportunities": opportunities[:8],
    }


def make_seo_tools(store: ActionStore | None = None, project_id: int | None = None) -> list[Tool]:
    """Build SEO tools. When store + project_id are given, every successful run
    caches its summary onto the project for the UI to read."""

    @tool
    async def audit_seo(url: str) -> str:
        """Run cheap structural SEO checks on a URL.

        Checks meta description, title length, h1 presence, og tags, image
        alts, structured data, robots.txt, sitemap.xml. Returns findings list
        with severity (high/medium/low) + fix instructions, plus the list of
        checks that already pass.

        Args:
            url: Full URL with https://.
        """
        result = await _audit_seo_impl(url)
        if result.get("ok") and store and project_id:
            store.set_seo_summary(project_id, result)
        return json.dumps(result, ensure_ascii=False)

    @tool
    async def check_pagespeed(url: str, strategy: str = "mobile") -> str:
        """Run Google PageSpeed Insights / Lighthouse on a URL.

        Returns performance / accessibility / SEO / best-practices scores plus
        Core Web Vitals (LCP, FCP, CLS, TBT) and the top opportunities.
        Slow (5-15s).

        Args:
            url: Full URL with https://.
            strategy: 'mobile' (default) or 'desktop'.
        """
        result = await _pagespeed_impl(url, strategy)
        if result.get("ok") and store and project_id:
            existing = {}
            proj = store.get_project(project_id)
            if proj and proj.get("pagespeed_summary"):
                existing = proj["pagespeed_summary"]
            existing[strategy] = result
            existing["url"] = result["url"]
            existing["captured_at"] = result.get("captured_at") or __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
            store.set_pagespeed_summary(project_id, existing)
        return json.dumps(result, ensure_ascii=False)

    return [audit_seo, check_pagespeed]
