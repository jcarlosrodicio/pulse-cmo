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

from datetime import datetime, timezone
from typing import Any

import structlog

from .brief import brief_context_block
from .llm import LLM, Message
from .store import ActionStore
from .text import parse_json_lenient, strip_draft_preamble, strip_stray_cjk

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
        "brain": project.get("product_brain") or store.get_product_brain(project_id),
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
    if "brain" in include and ev.get("brain"):
        from .product_brain import brain_context_block  # lazy: avoids import cycle

        b = brain_context_block(ev["brain"])
        if b:
            blocks.append(b)
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
    # Positioning is only as sharp as the product understanding it stands on —
    # ensure the Product Brain exists first (build it if this is a standalone call).
    if not ev.get("brain"):
        from .product_brain import generate_product_brain

        await generate_product_brain(llm, store, project_id)
        ev = gather_evidence(store, project_id)
    evidence_block = render_evidence(
        ev, include=("brain", "product", "brief", "crawl", "seo", "traction", "competitors")
    )
    user = evidence_block + "\n\nProduce the positioning diagnosis. Output only the JSON object."
    raw = await llm.complete(
        [Message(role="system", content=_POSITIONING_SYSTEM), Message(role="user", content=user)],
        temperature=0.45,
        max_tokens=20000,
        json_mode=True,
    )
    pos = parse_json(raw)
    if not isinstance(pos, dict) or not pos.get("value_prop"):
        log.warning(
            "positioning_parse_failed",
            project_id=project_id,
            raw_len=len(raw or ""),
            parsed_type=type(pos).__name__,
            parsed_keys=sorted(pos.keys())[:20] if isinstance(pos, dict) else [],
        )
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


# ---------------------------------------------------------------------------
# CRITIC — generate → verify → revise. A SEPARATE grounded pass (intrinsic
# self-critique is fragile) that rewrites generic/off-wedge output and strips
# meta-narration. Bounded to one revision.
# ---------------------------------------------------------------------------

_CRITIC_SYSTEM = (
    "You are a ruthless editor for an indie founder's marketing. You get a DRAFT "
    "and the product's brain. Make the draft specific to THIS product, or cut the "
    "generic parts. Keep its markdown format and voice.\n\n"
    "Apply these tests and REWRITE to fix every failure:\n"
    "- GENERIC TEST: would this line appear unchanged in a different product's "
    "plan? If yes, rewrite it to name the product's specific WEDGE, a real "
    "feature, the ICP, or a named competitor — or delete it.\n"
    "- WEDGE TEST: does it reflect the actual WEDGE (below), not the generic "
    "category? If not, refocus it.\n"
    "- VOCABULARY: prefer the ICP's own words (below) over marketing speak.\n"
    "- NO META: delete any narration ('Let me analyze', 'Here's the plan', "
    "'Sure,', 'I'll write', 'Okay,') — output the artifact only.\n"
    "- Keep what's already specific and good. Don't pad, don't add preamble.\n\n"
    "Output ONLY the revised artifact in the same markdown format. No commentary, "
    "no preface. English only."
)


async def critique_revise(
    llm: LLM, *, kind: str, draft: str, brain: dict[str, Any] | None
) -> str:
    """One grounded critic pass: rewrite generic/off-wedge content + strip
    meta-narration. Returns the revised draft (falls back to the cleaned
    original on any failure)."""
    cleaned = strip_stray_cjk(strip_draft_preamble(draft or "")).strip()
    if not cleaned or not brain:
        return cleaned
    from .product_brain import brain_context_block

    user = (
        brain_context_block(brain)
        + f"\n\nDRAFT (a {kind}):\n{cleaned}\n\n"
        f"Rewrite per the rules. Output only the revised {kind}."
    )
    try:
        revised = await llm.complete(
            [Message(role="system", content=_CRITIC_SYSTEM), Message(role="user", content=user)],
            temperature=0.4,
            max_tokens=20000,
        )
    except Exception as e:
        log.warning("critique_revise_failed", kind=kind, error=repr(e))
        return cleaned
    revised = strip_stray_cjk(strip_draft_preamble(revised or "")).strip()
    # guard against a critic that returns something degenerate/empty
    return revised if len(revised) >= max(40, len(cleaned) // 3) else cleaned


# ---------------------------------------------------------------------------
# THE GTM LOOP — bet -> weekly plan -> reality -> the call.
#
# This is the operator, not the artifact factory. Positioning says what to say;
# the bet says where to fight (ONE channel, with the play); the weekly plan says
# what to do this week; the review reads real numbers and makes the call. Each is
# a single grounded LLM call producing structured JSON — no agent fan-out, no
# generic checklist, nothing that ships without naming the wedge or the ICP.
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- prompt context blocks (compact, for grounding the loop calls) ----------

def channel_bet_block(bet: dict[str, Any] | None) -> str:
    if not bet:
        return ""
    play = bet.get("play") or {}
    return (
        "THE CHANNEL BET (committed — everything this week serves THIS):\n"
        f"  channel: {bet.get('channel', '')}\n"
        f"  why this one: {bet.get('why_this_one', '')}\n"
        f"  play asset: {play.get('asset', '')}\n"
        f"  cadence: {play.get('cadence', '')}\n"
        f"  targets: {play.get('targets', '')}\n"
        f"  leading indicator: {bet.get('leading_indicator', '')}\n"
        f"  kill criteria: {bet.get('kill_criteria', '')}"
    )


def _plan_block(plan: dict[str, Any] | None) -> str:
    if not plan:
        return "(no plan yet)"
    lines = [f"focus: {plan.get('focus', '')}"]
    for i, m in enumerate(plan.get("moves") or [], 1):
        done = " [DONE]" if m.get("done") else ""
        lines.append(f"  {i}. {m.get('move', '')}{done} (indicator: {m.get('leading_indicator', '')})")
    return "\n".join(lines)


def _snapshot_block(s: dict[str, Any] | None) -> str:
    if not s:
        return "(the founder gave no numbers)"
    lines: list[str] = []
    if s.get("signups") not in (None, ""):
        lines.append(f"new signups/users this week: {s.get('signups')}")
    if s.get("visitors") not in (None, ""):
        lines.append(f"visitors/traffic: {s.get('visitors')}")
    if s.get("top_sources"):
        lines.append(f"where they came from: {s.get('top_sources')}")
    if s.get("shipped"):
        lines.append(f"what the founder actually shipped/did: {s.get('shipped')}")
    if s.get("notes"):
        lines.append(f"founder notes: {s.get('notes')}")
    return "\n".join(lines) or "(the founder gave no numbers)"


def _review_block(r: dict[str, Any] | None) -> str:
    if not r:
        return ""
    return (
        f"what moved: {r.get('what_moved', '')}\n"
        f"the call: {r.get('the_call', '')} (kind: {r.get('call_kind', '')})\n"
        f"next focus: {r.get('next_focus', '')}"
    )


# --- THE BET — pick ONE channel and the play -------------------------------

_BET_SYSTEM = (
    "You are a GTM operator picking ONE channel for an indie founder to bet on for "
    "the next month. Not a ranked list — ONE channel, the single highest-fit one, "
    "with the exact play to run on it. Concentration beats spray at 0->1.\n\n"
    + ANALYST_STYLE
    + "\n\n"
    + GUARDRAIL_BLOCK
    + "\n\nYou have the product brain (wedge, ICP, the ICP's own vocabulary, the "
    "communities they live in), the positioning diagnosis (which already ranked "
    "channels), the founder's brief (goal, constraints, what they can produce), and "
    "real competitor reads. Pick the channel that (a) reaches THIS ICP where they "
    "already are, (b) fits the product's price/motion and the founder's constraints, "
    "and (c) a solo founder can actually sustain.\n\n"
    "Output STRICT JSON only, no preface, no fences:\n"
    "{\n"
    '  "channel": "<one channel, specific — not \'social media\' but e.g. '
    '\'r/<sub> + 2 adjacent subs\', \'comparison-page SEO\', \'Show HN + '
    'build-in-public on X\'>",\n'
    '  "why_this_one": "<3-4 sentences grounded in the ICP + product economics + the '
    'wedge. Name the ICP and the wedge explicitly.>",\n'
    '  "why_not_runner_up": "<1-2 sentences: the second-best channel and why it waits '
    '(not never)>",\n'
    '  "play": {\n'
    '     "asset": "<the ONE repeatable asset/motion this channel runs on, specific '
    'to the wedge — e.g. \'one <X> vs <Y> teardown per competitor pair\', not '
    '\'post content\'>",\n'
    '     "cadence": "<realistic for a solo founder, e.g. \'2x per week\'>",\n'
    '     "targets": "<the exact places/terms/people — named subs, search queries, '
    'account types — drawn from the brain\'s communities + vocabulary>",\n'
    '     "first_asset": "<the very first concrete asset to make this week>"\n'
    "  },\n"
    '  "leading_indicator": "<the early signal within ~2 weeks that says this is '
    'working — a real number, tied to the brief\'s goal>",\n'
    '  "kill_criteria": "<a specific result-by-date that means abandon this channel '
    'and switch>"\n'
    "}\n\n"
    "The channel must be one the positioning or brain actually supports. Never pick "
    "a channel the guardrails forbid or that the founder said already flopped. Be "
    "concrete enough that the founder knows exactly what to do tomorrow."
)


async def generate_channel_bet(
    llm: LLM, store: ActionStore, project_id: int, *, avoid_channel: str | None = None
) -> dict[str, Any]:
    """Commit the ONE channel bet (channel + the play + leading indicator + kill
    criteria). Persists it on the project and returns it. Builds the brain +
    positioning first if they're missing."""
    ev = gather_evidence(store, project_id)
    if not ev.get("brain"):
        from .product_brain import generate_product_brain

        await generate_product_brain(llm, store, project_id)
        ev = gather_evidence(store, project_id)
    if not ev.get("positioning"):
        await generate_positioning(llm, store, project_id)
        ev = gather_evidence(store, project_id)

    block = render_evidence(
        ev, include=("brain", "product", "brief", "positioning", "competitors")
    )
    if avoid_channel:
        block += (
            f"\n\nThe channel '{avoid_channel}' was just KILLED after a fair test — "
            "do NOT pick it again. Choose the next best channel."
        )
    user = block + "\n\nPick the one channel and the play. Output only the JSON object."
    # glm-5 is a reasoning model — it monologues before the JSON, so give it real
    # headroom (reasoning + the full object) and force json output.
    raw = await llm.complete(
        [Message(role="system", content=_BET_SYSTEM), Message(role="user", content=user)],
        temperature=0.4,
        max_tokens=2400,
        json_mode=True,
    )
    bet = parse_json(raw)
    if not isinstance(bet, dict) or not bet.get("channel") or not (bet.get("play") or {}).get("asset"):
        log.warning("channel_bet_parse_failed", project_id=project_id)
        return {}
    bet["committed_at"] = _now()
    store.set_channel_bet(project_id, bet)
    return bet


# --- THE WEEKLY PLAN — exactly 3 moves -------------------------------------

_WEEKPLAN_SYSTEM = (
    "You are a GTM operator writing THIS WEEK's plan for an indie founder who has "
    "committed to one channel bet. Exactly 3 moves. Each move is shippable by a solo "
    "founder in under 2 hours, serves the bet's play, and has a leading indicator it "
    "should move. No vague 'engage the community'. No busywork. No firehose of posts."
    "\n\n"
    + ANALYST_STYLE
    + "\n\nOutput STRICT JSON only, no preface, no fences:\n"
    "{\n"
    '  "focus": "<one sentence: what this week is about, tied to the bet>",\n'
    '  "moves": [\n'
    '     {"move": "<concrete action serving the play>", "leading_indicator": '
    '"<the number it should move>", "why": "<1 line tying it to the bet/wedge>"}\n'
    "  ]\n"
    "}\n\n"
    "Exactly 3 moves, no more. If a prior week's review is provided, this week MUST "
    "respond to it — double down on what moved, drop what didn't. If there's no prior "
    "week, start with the bet's first_asset as move 1."
)


async def generate_weekly_plan(
    llm: LLM, store: ActionStore, project_id: int, *, prior_review: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Produce this week's 3 moves and open a new gtm_weeks row. Returns the week
    dict (with id + week_num). Commits the bet first if there isn't one yet."""
    bet = store.get_channel_bet(project_id)
    if not bet:
        bet = await generate_channel_bet(llm, store, project_id)
    if not bet:
        return {}

    ev = gather_evidence(store, project_id)
    block = render_evidence(ev, include=("brain", "product", "brief"))
    block += "\n\n" + channel_bet_block(bet)
    if prior_review:
        block += "\n\nLAST WEEK'S REVIEW (this week must respond to it):\n" + _review_block(prior_review)
    user = block + "\n\nWrite this week's exactly-3 moves. Output only the JSON object."
    raw = await llm.complete(
        [Message(role="system", content=_WEEKPLAN_SYSTEM), Message(role="user", content=user)],
        temperature=0.45,
        max_tokens=2400,
        json_mode=True,
    )
    parsed = parse_json(raw)
    if not isinstance(parsed, dict) or not parsed.get("moves"):
        log.warning("weekly_plan_parse_failed", project_id=project_id)
        return {}
    moves: list[dict[str, Any]] = []
    for m in (parsed.get("moves") or [])[:3]:
        if not isinstance(m, dict) or not (m.get("move") or "").strip():
            continue
        moves.append({
            "move": m["move"].strip(),
            "leading_indicator": (m.get("leading_indicator") or "").strip(),
            "why": (m.get("why") or "").strip(),
            "done": False,
        })
    if not moves:
        return {}
    plan = {"focus": (parsed.get("focus") or "").strip(), "moves": moves}
    return store.create_gtm_week(project_id, plan=plan)


# --- THE CALL — read reality, decide, replan -------------------------------

_REVIEW_SYSTEM = (
    "You are a GTM operator doing the weekly review with an indie founder. You have "
    "the channel bet, this week's 3 moves, and the founder's ACTUAL numbers for the "
    "week (signups, where they came from, what they shipped). Read reality honestly. "
    "Attribute results to moves where you can; mark guesses [hypothesis]. Then make "
    "THE CALL: continue the bet, adjust the play, or kill the channel and switch.\n\n"
    + ANALYST_STYLE
    + "\n\nOutput STRICT JSON only, no preface, no fences:\n"
    "{\n"
    '  "what_moved": "<2-4 sentences: what the numbers say vs the moves. Be honest if '
    'nothing moved.>",\n'
    '  "attribution": "<best link between what shipped and what moved; mark '
    '[hypothesis] if unsure>",\n'
    '  "the_call": "<the decision + the reason, specific to the founder\'s '
    'situation>",\n'
    '  "call_kind": "continue|adjust|kill",\n'
    '  "next_focus": "<what next week should focus on, given the call>"\n'
    "}\n\n"
    "Be decisive but fair: 'continue' if the leading indicator moved; 'adjust' if "
    "mixed or the play needs a tweak; 'kill' ONLY if the channel clearly produced "
    "nothing after a fair test. Don't flip-flop on one week of thin data — if it's "
    "too early to tell, say 'continue' and name exactly what you need to see next."
)


async def run_weekly_review(
    llm: LLM, store: ActionStore, project_id: int, snapshot: dict[str, Any]
) -> dict[str, Any]:
    """The loop's heartbeat. Reads the founder's weekly numbers against the plan,
    writes the review + snapshot onto the current week, re-bets if the call is
    'kill', generates next week's plan, and refreshes the GTM Plan document.
    Returns {"review", "week"} (week = the newly opened next week)."""
    week = store.current_gtm_week(project_id)
    if not week:
        # No active week (e.g. first dive never ran the bet) — just open one.
        new_week = await generate_weekly_plan(llm, store, project_id)
        render_gtm_plan_doc(store, project_id)
        return {"review": None, "week": new_week}

    bet = store.get_channel_bet(project_id) or {}
    ev = gather_evidence(store, project_id)
    block = render_evidence(ev, include=("brain", "product", "brief"))
    block += "\n\n" + channel_bet_block(bet)
    block += "\n\nTHIS WEEK'S PLAN:\n" + _plan_block(week.get("plan"))
    block += "\n\nTHE FOUNDER'S NUMBERS THIS WEEK:\n" + _snapshot_block(snapshot)
    user = block + "\n\nDo the review and make the call. Output only the JSON object."
    raw = await llm.complete(
        [Message(role="system", content=_REVIEW_SYSTEM), Message(role="user", content=user)],
        temperature=0.4,
        max_tokens=2400,
        json_mode=True,
    )
    review = parse_json(raw)
    if not isinstance(review, dict) or not review.get("the_call"):
        log.warning("weekly_review_parse_failed", project_id=project_id)
        review = {
            "what_moved": "Could not parse the review this time — re-run the weekly review.",
            "attribution": "",
            "the_call": "continue",
            "call_kind": "continue",
            "next_focus": (week.get("plan") or {}).get("focus", ""),
        }

    # Persist the founder's numbers + the call onto the week being reviewed.
    store.set_gtm_week_snapshot(week["id"], snapshot)
    store.set_gtm_week_review(week["id"], review)

    # Kill -> re-bet on a different channel before replanning.
    if review.get("call_kind") == "kill" and bet.get("channel"):
        await generate_channel_bet(llm, store, project_id, avoid_channel=bet.get("channel"))

    next_week = await generate_weekly_plan(llm, store, project_id, prior_review=review)
    render_gtm_plan_doc(store, project_id)
    return {"review": review, "week": next_week}


# --- the readable document (auto-surfaces in the Documents UI) -------------

def bet_to_markdown(bet: dict[str, Any]) -> str:
    play = bet.get("play") or {}
    parts = [
        "## The bet",
        f"**Channel:** {bet.get('channel', '—')}",
        "",
        bet.get("why_this_one", ""),
        "",
        "### The play",
        f"- **Asset:** {play.get('asset', '—')}",
        f"- **Cadence:** {play.get('cadence', '—')}",
        f"- **Targets:** {play.get('targets', '—')}",
    ]
    if play.get("first_asset"):
        parts.append(f"- **First asset:** {play['first_asset']}")
    parts += [
        "",
        f"**Leading indicator:** {bet.get('leading_indicator', '—')}",
        f"**Kill criteria:** {bet.get('kill_criteria', '—')}",
    ]
    if bet.get("why_not_runner_up"):
        parts += ["", f"_Runner-up held back: {bet['why_not_runner_up']}_"]
    return "\n".join(parts)


def week_to_markdown(week: dict[str, Any]) -> str:
    plan = week.get("plan") or {}
    parts = [f"## This week (week {week.get('week_num', '?')})"]
    if plan.get("focus"):
        parts += [f"**Focus:** {plan['focus']}", ""]
    for m in plan.get("moves") or []:
        check = "x" if m.get("done") else " "
        ind = m.get("leading_indicator", "")
        parts.append(f"- [{check}] **{m.get('move', '')}**" + (f" — _{ind}_" if ind else ""))
    return "\n".join(parts)


def review_to_markdown(review: dict[str, Any], week_num: int) -> str:
    parts = [f"## Last week's call (week {week_num})", review.get("what_moved", "")]
    if review.get("attribution"):
        parts += ["", f"_Attribution: {review['attribution']}_"]
    parts += ["", f"**The call:** {review.get('the_call', '')}"]
    return "\n".join(p for p in parts if p is not None)


def render_gtm_plan_doc(store: ActionStore, project_id: int) -> None:
    """Render the committed bet + this week's moves (+ last week's call, if any)
    into the 'gtm_plan' document so it shows up in the existing Documents view."""
    bet = store.get_channel_bet(project_id)
    weeks = store.list_gtm_weeks(project_id)
    if not bet and not weeks:
        return
    parts: list[str] = []
    if bet:
        parts.append(bet_to_markdown(bet))
    if weeks:
        parts.append(week_to_markdown(weeks[0]))
        # most recent reviewed week (skip the current open one)
        reviewed = next((w for w in weeks if w.get("review")), None)
        if reviewed and reviewed["id"] != weeks[0]["id"]:
            parts.append(review_to_markdown(reviewed["review"], reviewed.get("week_num", 0)))
    body = strip_stray_cjk("\n\n".join(p for p in parts if p)).strip()
    if not body:
        return
    store.upsert_document(
        project_id=project_id,
        kind="gtm_plan",
        title="GTM Plan",
        content_md=body,
        metadata={"bet": bet, "current_week": weeks[0] if weeks else None},
    )
