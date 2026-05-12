"""Reddit discovery + reply drafting.

Read-only — no posting. Uses Reddit's public JSON endpoints (no auth needed).
For copy-paste only; the user posts from their own account.

Reply drafting follows the spec's anti-spam rules:
  * lead with 5+ sentences of actual value
  * mention product only if it genuinely fits
  * match subreddit tone
  * avoid AI tells (em-dashes, "I'd love to", "happy to help", etc.)
  * second LLM pass to "humanize" the draft
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone

import httpx
import structlog

from ..llm import LLM, Message
from ..store import ActionStore
from ..text import strip_draft_preamble, strip_reasoning
from .registry import Tool, tool

log = structlog.get_logger()

REDDIT_HEADERS = {
    "User-Agent": "pulse-bot/0.1 (+https://pulse.cc) — read-only research",
    "Accept": "application/json",
}

HUMANIZE_RULES = """\
Rewrite the reply so it sounds unmistakably human, not AI.

HARD RULES:
- Remove every em-dash (—). Use periods or commas.
- Remove every "I'd love to", "happy to help", "let me know if you have questions",
  "I hope this helps", "feel free to", "as an AI", "delve into", "in this digital age",
  "leverage", "synergy", "robust", "comprehensive solution".
- Vary sentence length. Mix short punchy sentences with longer ones.
- Lowercase first letters are fine. Sentence fragments fine. Casual punctuation fine.
- No bullet lists unless the question genuinely needs them.
- No sign-offs like "Hope that helps!" or "Best of luck!"
- Keep length roughly the same. Do not add new content.

Output ONLY the rewritten reply text. No preface, no quotes, no explanation.\
"""


async def _search_reddit(query: str, subreddit: str | None = None, sort: str = "new", limit: int = 10) -> list[dict]:
    """Search Reddit using the public search JSON endpoint."""
    base = "https://www.reddit.com"
    if subreddit:
        url = f"{base}/r/{subreddit.lstrip('r/')}/search.json"
        params = {"q": query, "restrict_sr": "on", "sort": sort, "limit": str(limit), "t": "month"}
    else:
        url = f"{base}/search.json"
        params = {"q": query, "sort": sort, "limit": str(limit), "t": "month"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, headers=REDDIT_HEADERS, params=params)
        if r.status_code >= 400:
            log.warning("reddit_search_status", status=r.status_code, query=query, sub=subreddit)
            return []
        data = r.json()
    except Exception as e:
        log.warning("reddit_search_failed", error=repr(e), query=query)
        return []
    return [c.get("data", {}) for c in (data.get("data") or {}).get("children") or []]


def _format_post(post: dict) -> dict:
    return {
        "id": post.get("id"),
        "subreddit": post.get("subreddit"),
        "title": post.get("title"),
        "selftext": (post.get("selftext") or "")[:1200],
        "url": f"https://www.reddit.com{post.get('permalink', '')}",
        "score": post.get("score"),
        "num_comments": post.get("num_comments"),
        "author": post.get("author"),
        "created_utc": post.get("created_utc"),
        "age_hours": _age_hours(post.get("created_utc")),
        "is_question": _looks_like_question(post.get("title", ""), post.get("selftext", "")),
    }


def _age_hours(created_utc: float | None) -> float | None:
    if not created_utc:
        return None
    return round((datetime.now(timezone.utc).timestamp() - created_utc) / 3600, 1)


def _looks_like_question(title: str, body: str) -> bool:
    t = (title + " " + (body or "")).lower()
    return (
        "?" in t
        or any(t.startswith(p) for p in ("how do", "how can", "what's", "is there", "anyone know"))
        or any(p in t for p in ("recommend", "alternatives to", "looking for", "suggestions for"))
    )


@tool
async def find_reddit_opportunities(
    keywords: list[str],
    subreddits: list[str] = [],
    days_back: int = 14,
) -> str:
    """Search Reddit for recent posts where your product is relevant.

    Searches each keyword across Reddit globally and within priority
    subreddits if provided. Returns up to 10 fresh threads ranked by
    looks-like-a-question + recency. Read each thread before drafting a
    reply with draft_reddit_reply.

    Args:
        keywords: List of search terms (product, problem space, competitors).
        subreddits: Optional list of subreddit names ('SaaS', 'r/SideProject').
        days_back: Recency window for soft filtering (default 14, capped 30).
    """
    if not keywords:
        return json.dumps({"ok": False, "error": "keywords required"})
    days_back = max(1, min(int(days_back), 30))
    cutoff = (datetime.now(timezone.utc).timestamp() - days_back * 86400)

    seen: dict[str, dict] = {}

    tasks = []
    for kw in keywords[:5]:
        tasks.append(_search_reddit(kw, None, "new", 10))
        for sub in subreddits[:5]:
            tasks.append(_search_reddit(kw, sub, "new", 8))

    results = await asyncio.gather(*tasks, return_exceptions=False)
    for batch in results:
        for post in batch:
            pid = post.get("id")
            if not pid or pid in seen:
                continue
            if (post.get("created_utc") or 0) < cutoff:
                continue
            seen[pid] = _format_post(post)

    out = list(seen.values())
    # rank: questions first, then by recency (newer first)
    out.sort(key=lambda p: (not p["is_question"], -(p.get("created_utc") or 0)))
    return json.dumps(
        {"ok": True, "found": len(out), "items": out[:10]},
        ensure_ascii=False,
    )[:10000]


def make_reddit_tools(
    llm: LLM,
    store: ActionStore,
    project_id: int,
    run_id: int,
) -> list[Tool]:
    """Build Reddit tools bound to a run for persistence side-effects."""

    @tool
    async def draft_reddit_reply(
        post_url: str,
        post_title: str,
        post_body: str,
        subreddit: str,
        product_angle: str = "",
    ) -> str:
        """Draft a Reddit reply that genuinely helps + mentions the product naturally.

        Use ONLY after find_reddit_opportunities surfaced a relevant thread you
        read in full. Spec rules: 5+ sentences of value first, only mention the
        product if it actually fits the question. A second 'humanize' LLM pass
        scrubs AI tells. Saves the draft as a copy-paste action; no auto-post.

        Args:
            post_url: Direct Reddit thread URL.
            post_title: Title of the post we're replying to.
            post_body: Body text of the post (paste in full).
            subreddit: Subreddit name (without r/).
            product_angle: Optional hint about how the product fits ("we solve
                X" or "skip product mention — this is a generic Q").
        """
        bv = store.get_brand_voice(project_id) or {}
        wi = (store.get_project(project_id) or {}).get("writing_instructions") or {}
        reddit_extra = (wi.get("reddit") or {}).get("instructions", "")

        project = store.get_project(project_id) or {}
        product_name = project.get("name", "")
        product_desc = project.get("description", "")

        system = (
            "You draft Reddit replies that look like they were written by a real, "
            "helpful user — not by a product's marketing team.\n\n"
            "RULES (non-negotiable):\n"
            "1. LEAD with at least 5 sentences of substantive value answering the "
            "person's actual question. No preamble.\n"
            "2. Only mention the product if it GENUINELY fits — and even then, mention "
            "it as 'I built X for this' or '… I use X' rather than promoting it. "
            "If the product doesn't fit, write a reply with NO product mention.\n"
            "3. Match the subreddit's energy. r/SideProject is forgiving; r/programming "
            "and r/SaaS will roast obvious self-promo.\n"
            "4. NEVER use em-dashes. NEVER use 'I'd love to', 'happy to help', "
            "'let me know', 'hope this helps', 'feel free to'. No closing CTA.\n"
            "5. Vary sentence length. Allow casual lowercase and fragments. Real humans "
            "don't write in marketing voice.\n"
            "6. No bullet lists unless absolutely necessary.\n\n"
            f"Product context (use sparingly, only if relevant):\n"
            f"- Name: {product_name}\n"
            f"- About: {product_desc}\n"
            f"- Subreddit: r/{subreddit}\n"
        )
        if bv.get("tone"):
            system += f"- Author's tone: {bv['tone']}\n"
        if reddit_extra:
            system += f"\nUser's Reddit-specific instructions:\n{reddit_extra}\n"

        user = (
            f"REDDIT POST:\n"
            f"r/{subreddit}\n"
            f"Title: {post_title}\n"
            f"Body: {post_body}\n"
            f"URL: {post_url}\n\n"
            f"Angle: {product_angle or '(decide whether the product fits at all)'}\n\n"
            "Draft the reply. Output ONLY the reply text."
        )

        # First-pass: produce three angle variants in one call.
        variants_system = (
            system
            + "\n\nOUTPUT FORMAT (non-negotiable):\n"
            "- Produce EXACTLY 3 distinct reply variants. Each takes a different\n"
            "  angle (e.g. one with no product mention, one with subtle product mention,\n"
            "  one focused on shared experience).\n"
            "- Separate variants with this exact line on its own, nothing else on\n"
            "  that line:\n\n  ---VARIANT---\n\n"
            "- Do not number or label them. Start directly with the first reply."
        )
        first_pass_raw = await llm.complete(
            [Message(role="system", content=variants_system), Message(role="user", content=user)],
            temperature=0.9,
            max_tokens=2400,
        )
        raw_chunks = [c.strip() for c in first_pass_raw.split("---VARIANT---") if c.strip()]
        if not raw_chunks:
            raw_chunks = [first_pass_raw.strip()]

        # Humanize + scrub each variant individually (cheap — short text).
        humanized_variants: list[str] = []
        for chunk in raw_chunks[:3]:
            cleaned_first = strip_draft_preamble(strip_reasoning(chunk)).strip().strip('"').strip("'")
            humanized = await llm.complete(
                [
                    Message(role="system", content=HUMANIZE_RULES),
                    Message(role="user", content=cleaned_first),
                ],
                temperature=0.5,
                max_tokens=900,
            )
            humanized_variants.append(
                _scrub(strip_draft_preamble(strip_reasoning(humanized)).strip().strip('"').strip("'"))
            )
        while len(humanized_variants) < 3:
            humanized_variants.append(humanized_variants[-1])

        action_id = store.create_action(
            project_id=project_id,
            run_id=run_id,
            action_type="reddit_reply",
            title=f"r/{subreddit}: {post_title[:80]}",
            content=humanized_variants[0],
            context={
                "subreddit": subreddit,
                "post_url": post_url,
                "post_title": post_title,
                "product_angle": product_angle,
                "variants": humanized_variants,
                "chosen_variant": 0,
            },
        )
        return json.dumps(
            {
                "ok": True,
                "action_id": action_id,
                "draft_preview": humanized_variants[0][:300],
                "variants": len(humanized_variants),
            }
        )

    @tool
    async def log_reddit_opportunity(
        post_url: str,
        subreddit: str,
        title: str,
        why_relevant: str,
        suggested_angle: str,
    ) -> str:
        """Record a Reddit thread as a copy-paste opportunity without drafting a full reply.

        Use when the thread is relevant but needs the user's personal voice or
        nuance — you flag it; they read and reply themselves.

        Args:
            post_url: Reddit thread URL.
            subreddit: Subreddit name (without r/).
            title: Post title.
            why_relevant: One sentence on why it matches the product.
            suggested_angle: How they should approach a reply (not a draft).
        """
        action_id = store.create_action(
            project_id=project_id,
            run_id=run_id,
            action_type="reddit_opportunity",
            title=f"r/{subreddit}: {title[:80]}",
            content=(
                f"**Why relevant:** {why_relevant}\n\n"
                f"**Suggested angle:** {suggested_angle}\n\n"
                f"**Link:** {post_url}"
            ),
            context={
                "subreddit": subreddit,
                "post_url": post_url,
                "why": why_relevant,
                "angle": suggested_angle,
            },
        )
        return json.dumps({"ok": True, "action_id": action_id})

    return [find_reddit_opportunities, draft_reddit_reply, log_reddit_opportunity]


_AI_TELLS = [
    (r"—", ", "),
    (r"\bI'd love to\b", "I'd like to"),
    (r"\bI would love to\b", "I'd like to"),
    (r"\bhappy to help\b", ""),
    (r"\bhope this helps\b", ""),
    (r"\bfeel free to\b", ""),
    (r"\bdelve into\b", "look at"),
    (r"\bin this digital age\b", ""),
    (r"\bleverage\b", "use"),
    (r"\bsynergy\b", "fit"),
    (r"\brobust\b", "solid"),
    (r"\bcomprehensive solution\b", "tool"),
]


def _scrub(text: str) -> str:
    out = text
    for pat, repl in _AI_TELLS:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    out = re.sub(r"\s+([.,!?])", r"\1", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
