"""Shared strategic-analysis core.

The whole point of this module: NO strategic generator should ever again run on
just a name + a one-line description. Everything strategic — positioning, the
marketing plan, market gaps — calls `gather_evidence()` and reasons over the
REAL crawl, the REAL SEO/traction state, the REAL competitor reads, and the
founder's brief. `generate_positioning` produces the diagnosis spine (situation
→ ICP → value prop → wedge → channels → measurement) that the plan builds on,
so the output is a considered strategy, not a generic channel checklist.

Two cheap LLM calls do the work (positioning, then plan). Verification is baked
into the prompts: every claim is labeled [evidence] or [hypothesis] and missing
evidence is surfaced as open questions, rather than presented as fact.
"""

from __future__ import annotations

from typing import Any

import structlog

from .brief import brief_context_block
from .llm import LLM, Message
from .store import ActionStore
from .text import parse_json_lenient, strip_stray_cjk

log = structlog.get_logger()


# Canonical go-to-market guardrails — shared by launch, strategy, and
# positioning so the plan can never recommend what the launch module forbids
# (the old strategy generator happily suggested paid ads for a $9/mo indie tool
# and auto-DM spam; these stop that).
UNIVERSAL_GUARDRAILS = [
    "No paid ads for a no-LTV or pre-revenue product — spend never recovers.",
    "No automated DMs, auto-follow, or mass cold outreach — spammy and bannable.",
    "No mass cross-posting the same link to many subreddits — shadowban.",
    "Never ask for upvotes on HN / Product Hunt — gets flagged.",
    "Don't buy followers or engagement — vanity, zero conversions.",
    "Don't fire every channel on day one — wastes one-shots on an unproven funnel.",
    "Don't track retention on a one-time-use product — wrong yardstick.",
    "Never launch a share product with a broken OG unfurl — instant death.",
    "Don't recommend a tactic the founder said they already tried and that flopped.",
    "Don't invent a channel or feature that doesn't exist (e.g. 'DM them on HN').",
]

GUARDRAIL_BLOCK = "HARD CONSTRAINTS (never violate any):\n" + "\n".join(
    f"- {g}" for g in UNIVERSAL_GUARDRAILS
)

# Shared analyst voice: grounded, opinionated, English, no fluff.
ANALYST_STYLE = (
    "Respond in English only. Be specific and opinionated — never generic "
    "best-practice filler. Ground every claim in the evidence provided. When "
    "you assert something the evidence does NOT support, mark it [hypothesis] "
    "and say what would confirm it; mark grounded claims [evidence]. No "
    "marketing fluff, no em-dashes, no emojis. Specifics beat frameworks."
)


def parse_json(raw: str) -> Any | None:
    return parse_json_lenient(raw)


# ---------------------------------------------------------------------------
# Evidence gathering — pull everything persisted about the project.
# ---------------------------------------------------------------------------

def gather_evidence(store: ActionStore, project_id: int) -> dict[str, Any]:
    project = store.get_project(project_id) or {}
    pos = store.get_document_by_kind(project_id, "positioning")
    return {
        "project": project,
        "brief": project.get("brief") or store.get_brief(project_id),
        "crawl": project.get("crawl_summary"),
        "seo": project.get("seo_summary"),
        "traction": project.get("traction_summary"),
        "geo": project.get("geo_summary"),
        "competitor_reads": store.get_competitor_reads(project_id),
        "positioning": (pos or {}).get("metadata", {}).get("positioning") if pos else None,
        "product_info_md": (store.get_document_by_kind(project_id, "product_information") or {}).get("content_md", ""),
    }


def _render_competitor_reads(reads: list[dict[str, Any]]) -> str:
    if not reads:
        return ""
    lines = ["COMPETITORS (actually crawled — use this, not your training memory):"]
    for r in reads[:6]:
        name = r.get("name") or r.get("title") or r.get("url") or "competitor"
        desc = (r.get("description") or "").strip()
        body = (r.get("text") or "").strip()
        snippet = body[:500] if body else ""
        if not snippet and r.get("search_snippets"):
            snippet = " | ".join(
                f"{s.get('title','')}: {s.get('snippet','')}" for s in r["search_snippets"][:3]
            )[:500]
        lines.append(f"- {name} ({r.get('url','')})")
        if desc:
            lines.append(f"    pitch: {desc}")
        if snippet:
            lines.append(f"    crawled: {snippet}")
    return "\n".join(lines)


def _render_seo(seo: dict[str, Any] | None) -> str:
    if not seo or not isinstance(seo, dict):
        return ""
    score = seo.get("score")
    findings = seo.get("findings") or []
    top = [f for f in findings if f.get("severity") in ("high", "medium")][:5]
    if score is None and not top:
        return ""
    out = [f"SEO STATE: on-page score {score}/100" if score is not None else "SEO STATE:"]
    for f in top:
        out.append(f"    [{f.get('severity')}] {f.get('category')}: {f.get('description')}")
    return "\n".join(out)


def _render_traction(traction: dict[str, Any] | None) -> str:
    if not traction or not isinstance(traction, dict) or traction.get("status") != "done":
        return ""
    totals = traction.get("totals") or {}
    out = [
        f"TRACTION: {totals.get('mentions', 0)} mentions across "
        f"{totals.get('platforms', 0)} platforms; strongest: {traction.get('strongest') or 'none'}"
    ]
    for ins in (traction.get("insights") or [])[:4]:
        out.append(f"    - {ins}")
    return "\n".join(out)


def render_evidence(ev: dict[str, Any], *, include: tuple[str, ...]) -> str:
    """Render the requested evidence sections into a compact prompt block."""
    p = ev.get("project") or {}
    blocks: list[str] = []
    if "product" in include:
        comps = ", ".join(p.get("competitors") or []) or "(none known)"
        blocks.append(
            f"PRODUCT: {p.get('name')} ({p.get('url')})\n"
            f"DESCRIPTION: {p.get('description') or '(none)'}\n"
            f"KNOWN COMPETITORS: {comps}"
        )
    if "brief" in include:
        b = brief_context_block(ev.get("brief"))
        if b:
            blocks.append(b)
    if "crawl" in include and ev.get("crawl"):
        c = ev["crawl"]
        txt = (c.get("text") or "")[:3500]
        repo = c.get("repo")
        if repo:
            blocks.append(
                "REPO EVIDENCE: "
                f"{repo.get('stars')} stars, {repo.get('language')}, "
                f"topics: {', '.join(repo.get('topics') or [])}\n{txt}"
            )
        elif txt:
            blocks.append(f"WHAT THE SITE ACTUALLY SAYS (crawled):\n{txt}")
    if "seo" in include:
        s = _render_seo(ev.get("seo"))
        if s:
            blocks.append(s)
    if "traction" in include:
        t = _render_traction(ev.get("traction"))
        if t:
            blocks.append(t)
    if "competitors" in include:
        c = _render_competitor_reads(ev.get("competitor_reads") or [])
        if c:
            blocks.append(c)
    if "positioning" in include and ev.get("positioning"):
        pos = ev["positioning"]
        wedge = pos.get("wedge") or {}
        blocks.append(
            "POSITIONING (already diagnosed this run — build on it):\n"
            f"    value prop: {pos.get('value_prop')}\n"
            f"    wedge: {wedge.get('move')} ({wedge.get('why')})\n"
            f"    north star: {(pos.get('measurement') or {}).get('north_star')}"
        )
    return "\n\n".join(b for b in blocks if b)


# ---------------------------------------------------------------------------
# POSITIONING — the diagnosis spine.
# ---------------------------------------------------------------------------

_POSITIONING_SYSTEM = (
    "You are a sharp head of growth doing the first strategic diagnosis of an "
    "indie product. You have the crawl, the SEO/traction state, real competitor "
    "reads, and the founder's brief. Produce a POSITIONING DIAGNOSIS, not a "
    "to-do list.\n\n"
    + ANALYST_STYLE
    + "\n\n"
    + GUARDRAIL_BLOCK
    + "\n\nOutput STRICT JSON only, no preface, no fences:\n"
    "{\n"
    '  "situation": "<3-4 sentence honest read: what this is, who buys, the one '
    'real obstacle to growth>",\n'
    '  "icp": "<the specific beachhead segment to win first>",\n'
    '  "jtbd": "<the job the ICP hires this product to do>",\n'
    '  "value_prop": "<one line: for <icp> who <need>, <product> is the <category> '
    'that <core benefit>, unlike <named competitor>>",\n'
    '  "wedge": { "move": "<the single sharpest GTM motion to own>", "why": '
    '"<why this beats fighting on the incumbent\'s axis>", "confidence": '
    '"evidence|hypothesis" },\n'
    '  "differentiation": ["vs <named competitor>: <the real, crawled '
    'difference>"],\n'
    '  "channels": [ { "channel": "<name>", "why": "<why it fits THIS product + '
    'ICP>", "leading_indicator": "<the early metric that proves it works>", '
    '"effort": "low|med|high" } ],\n'
    '  "measurement": { "north_star": "<the one metric tied to the brief\'s '
    'goal>", "leading_indicators": ["<2-4 early signals>"] },\n'
    '  "open_questions": ["<what evidence is missing / what to validate before '
    'betting big>"]\n'
    "}\n\n"
    "Rules: rank 3-5 channels, best-fit first; kill channels that don't fit the "
    "product type or the founder's constraints and DON'T list them. The wedge is "
    "the most important field — if the product is fighting an incumbent on the "
    "incumbent's own axis (e.g. 'more models' vs an aggregator), name what it "
    "should own instead. Tie the north star to the brief's stated goal if there "
    "is one."
)


def positioning_to_markdown(pos: dict[str, Any]) -> str:
    """Render the positioning JSON into the readable document body."""
    wedge = pos.get("wedge") or {}
    meas = pos.get("measurement") or {}
    parts = [
        "## Situation", pos.get("situation", "—"), "",
        "## Ideal customer (beachhead)", pos.get("icp", "—"), "",
        f"**Job to be done:** {pos.get('jtbd', '—')}", "",
        "## Value proposition", pos.get("value_prop", "—"), "",
        "## The wedge",
        f"**{wedge.get('move', '—')}**  ({wedge.get('confidence', 'hypothesis')})", "",
        wedge.get("why", ""), "",
    ]
    diff = pos.get("differentiation") or []
    if diff:
        parts.append("## Differentiation")
        parts += [f"- {d}" for d in diff]
        parts.append("")
    chans = pos.get("channels") or []
    if chans:
        parts.append("## Channel priorities")
        for c in chans:
            parts.append(
                f"- **{c.get('channel')}** ({c.get('effort','?')} effort) — {c.get('why','')} "
                f"_Leading indicator: {c.get('leading_indicator','—')}_"
            )
        parts.append("")
    parts.append("## How we'll measure")
    parts.append(f"**North star:** {meas.get('north_star', '—')}")
    li = meas.get("leading_indicators") or []
    if li:
        parts += [f"- {x}" for x in li]
    oq = pos.get("open_questions") or []
    if oq:
        parts += ["", "## Open questions (validate before betting big)"]
        parts += [f"- {q}" for q in oq]
    return "\n".join(parts).strip()


async def generate_positioning(
    llm: LLM, store: ActionStore, project_id: int
) -> dict[str, Any]:
    """Run the diagnosis. Saves a 'positioning' document and returns the JSON.
    Downstream generators (strategy, gaps) consume it."""
    ev = gather_evidence(store, project_id)
    evidence_block = render_evidence(
        ev, include=("product", "brief", "crawl", "seo", "traction", "competitors")
    )
    user = evidence_block + "\n\nProduce the positioning diagnosis. Output only the JSON object."
    raw = await llm.complete(
        [Message(role="system", content=_POSITIONING_SYSTEM), Message(role="user", content=user)],
        temperature=0.45,
        max_tokens=1800,
    )
    pos = parse_json(raw)
    if not isinstance(pos, dict) or not pos.get("value_prop"):
        log.warning("positioning_parse_failed", project_id=project_id)
        return {}
    body = strip_stray_cjk(positioning_to_markdown(pos))
    store.upsert_document(
        project_id=project_id,
        kind="positioning",
        title="Positioning & Strategy",
        content_md=body,
        metadata={"positioning": pos},
    )
    return pos
