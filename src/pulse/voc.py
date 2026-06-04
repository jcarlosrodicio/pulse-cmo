"""Voice-of-customer mining.

The old Reddit/HN feature was an "opportunity firehose" that surfaced nothing
useful. Its real value was never "20 threads to reply to" — it was learning how
real buyers describe the problem and what they hate about the alternatives. This
module captures THAT: it runs the Product Brain's own search seeds against real
forum/search results, distills the exact language people use, and merges a
`voice` block back into the brain. Every downstream message (positioning, the
bet, content) then speaks in the customer's own words instead of marketing
speak. Degrades gracefully — if the searches are thin or fail, the base brain is
kept untouched.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog

from .llm import LLM, Message
from .product_brain import brain_context_block
from .store import ActionStore
from .text import parse_json_lenient
from .tools.registry import Tool, tool
from .tools.web import _WebClient

log = structlog.get_logger()


_VOICE_SYSTEM = (
    "You extract the VOICE OF THE CUSTOMER from real forum posts and search "
    "snippets. Work ONLY from the snippets provided — never invent. Pull the "
    "EXACT words real people use about this problem and what they dislike about "
    "the alternatives. If the snippets don't support a field, leave it empty.\n\n"
    "Output STRICT JSON only, no preface, no fences:\n"
    "{\n"
    '  "pains": ["<a real frustration in the customer\'s own words, lifted from a '
    'snippet>"],\n'
    '  "alternative_gripes": [{"alternative": "<a tool/method they complain '
    'about>", "gripe": "<what they dislike, in their words>"}],\n'
    '  "vocabulary": ["<words/phrases real people use for this space — not '
    'marketing speak>"],\n'
    '  "quotes": [{"text": "<a short verbatim quote>", "source": "<url or '
    'site>"}]\n'
    "}\n\n"
    "Use only language actually present in the snippets. Up to 8 pains, 6 gripes, "
    "10 vocabulary, 5 quotes. Output ONLY the JSON object."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _items(data: Any) -> list[dict[str, Any]]:
    """Normalize the search API's results into [{title, url, snippet}]."""
    if isinstance(data, list):
        items = data
    else:
        items = (
            (data or {}).get("results")
            or (data or {}).get("data")
            or (data or {}).get("items")
            or []
        )
        if isinstance(items, dict):
            items = items.get("items") or items.get("results") or []
    out: list[dict[str, Any]] = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        out.append({
            "title": it.get("title") or it.get("name") or "",
            "url": it.get("url") or it.get("link") or "",
            "snippet": (it.get("snippet") or it.get("description") or it.get("content") or "").strip(),
        })
    return out


async def enrich_brain_with_voice(
    llm: LLM, store: ActionStore, project_id: int, *, base_url: str, api_key: str
) -> dict[str, Any]:
    """Mine real customer language using the brain's search seeds and merge a
    `voice` block into the brain. Returns the (possibly enriched) brain. Never
    raises; keeps the base brain on any failure or thin signal."""
    brain = store.get_product_brain(project_id)
    if not brain or not api_key:
        return brain or {}

    seeds = brain.get("search_seeds") or {}
    queries: list[str] = []
    for k in ("pain", "switching", "question", "comparison"):
        for q in (seeds.get(k) or [])[:2]:
            if q and q not in queries:
                queries.append(q)
    queries = queries[:6]
    if not queries:
        return brain

    client = _WebClient(base_url=base_url, api_key=api_key, timeout=30.0)
    sem = asyncio.Semaphore(4)

    async def _one(q: str) -> tuple[str, list[dict[str, Any]]]:
        async with sem:
            try:
                data = await client.post("/v1/tools/search", {"query": q, "num_results": 5})
                return q, _items(data)
            except Exception:
                return q, []

    pairs = await asyncio.gather(*[_one(q) for q in queries])
    snippets: list[str] = []
    for q, items in pairs:
        for it in items[:4]:
            s = it.get("snippet")
            if s:
                snippets.append(f"[{q}] {it.get('title', '')}: {s} ({it.get('url', '')})"[:320])

    if len(snippets) < 3:
        log.info("voc_thin", project_id=project_id, snippets=len(snippets))
        return brain

    user = (
        brain_context_block(brain)
        + "\n\nREAL POSTS / SNIPPETS (verbatim from web search):\n"
        + "\n".join(snippets[:24])
        + "\n\nExtract the voice of the customer. Output only the JSON object."
    )
    try:
        raw = await llm.complete(
            [Message(role="system", content=_VOICE_SYSTEM), Message(role="user", content=user)],
            temperature=0.3,
            max_tokens=2000,
            json_mode=True,
        )
    except Exception as e:
        log.warning("voc_distill_failed", project_id=project_id, error=repr(e))
        return brain

    voice = parse_json_lenient(raw)
    if isinstance(voice, dict) and (voice.get("pains") or voice.get("quotes")):
        brain["voice"] = {
            "pains": (voice.get("pains") or [])[:8],
            "alternative_gripes": [g for g in (voice.get("alternative_gripes") or [])[:6] if isinstance(g, dict)],
            "vocabulary": (voice.get("vocabulary") or [])[:10],
            "quotes": [q for q in (voice.get("quotes") or [])[:5] if isinstance(q, dict)],
            "sourced_at": _now(),
        }
        store.set_product_brain(project_id, brain)
        log.info("voc_enriched", project_id=project_id, pains=len(brain["voice"]["pains"]))
    return brain


def make_voc_tools(
    *, llm: LLM, store: ActionStore, project_id: int, base_url: str, api_key: str
) -> list[Tool]:

    @tool
    async def mine_customer_voice() -> str:
        """Mine the VOICE OF THE CUSTOMER and fold it into the Product Brain.

        Runs the brain's own search seeds against real forum/search results,
        extracts how real people describe the problem and what they dislike about
        the alternatives (their exact words), and merges it into the brain so
        every later message is grounded in the customer's language. Call ONCE on
        the first dive AFTER build_product_brain and BEFORE positioning. No args.
        """
        brain = await enrich_brain_with_voice(
            llm, store, project_id, base_url=base_url, api_key=api_key
        )
        voice = (brain or {}).get("voice") or {}
        if not voice:
            return json.dumps({
                "ok": True,
                "note": "no strong voice signal found — using the base brain (vocabulary from the crawl)",
                "pains": 0,
            })
        return json.dumps({
            "ok": True,
            "pains": len(voice.get("pains") or []),
            "gripes": len(voice.get("alternative_gripes") or []),
            "sample_pain": (voice.get("pains") or [""])[0][:140],
        })

    return [mine_customer_voice]
