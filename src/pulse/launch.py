"""Launch mode — archetype-driven go-to-market workflow.

Implements the CMO-AGENT-LAUNCH-PLAYBOOK as a state machine:

    INTAKE   → collect/confirm the product facts (Part 2 schema)
    CLASSIFY → map to one of six growth archetypes (Part 3 table)
    PLAN     → render positioning + channel sequence + Week-1 board + tracking
    ACTIVE   → daily TRACK loop: ingest scorecard, apply decision rules,
               output "today's move"
    DONE     → retrospective

The core IP is the archetype table below: classify the product correctly and
the growth engine, north-star metric, channels, sequencing, and anti-patterns
all fall out deterministically. The LLM customizes the *content*; the table
fixes the *shape*.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from .llm import LLM, Message

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# PART 3 — the archetype table (the core IP), as structured data.
# Each `target` maps a channel to a Pulse targeted-run kind so the ASSETS
# phase can wire "generate this post" buttons to the right draft tool.
# ---------------------------------------------------------------------------

ARCHETYPES: dict[str, dict[str, Any]] = {
    "viral_artifact": {
        "label": "Viral artifact / generator",
        "blurb": "Wrapped-style, 'rate my X' — a shareable artifact IS the ad.",
        "growth_engine": "The artifact spreads on share; growth is the loop, not the founder's audience or ads.",
        "north_star": "Total artifacts created",
        "loop_metric": "Viral coefficient K = re-creates ÷ creates",
        "metric_labels": {"north": "Artifacts", "loop": "Re-creates", "visits": "Visits"},
        "channels": [
            {"name": "Reddit (soft launch)", "type": "repeatable", "target": "reddit_reply"},
            {"name": "Short-form video (IG/TikTok/Reels)", "type": "repeatable", "target": None},
            {"name": "Show HN", "type": "one_shot", "target": "hn_post"},
            {"name": "Product Hunt", "type": "one_shot", "target": None},
            {"name": "Niche communities", "type": "repeatable", "target": "reddit_opportunity"},
        ],
        "avoid": ["Paid ads", "retention/DAU as the yardstick", "follower-count dependence"],
    },
    "dev_tool": {
        "label": "Dev tool / API / library",
        "blurb": "Content + community + DX word-of-mouth.",
        "growth_engine": "Developers adopt via great docs, a Show HN moment, and word of mouth in technical communities.",
        "north_star": "Signups → activation (first successful use)",
        "loop_metric": "Time-to-first-value",
        "metric_labels": {"north": "Signups", "loop": "Activations", "visits": "Visits"},
        "channels": [
            {"name": "Show HN", "type": "one_shot", "target": "hn_post"},
            {"name": "Reddit (niche tech subs)", "type": "repeatable", "target": "reddit_reply"},
            {"name": "Docs / SEO", "type": "repeatable", "target": "article"},
            {"name": "Dev Discords", "type": "repeatable", "target": None},
            {"name": "DevRel content", "type": "repeatable", "target": "article"},
        ],
        "avoid": ["Consumer social", "influencer spend", "hype with no docs"],
    },
    "b2b_saas": {
        "label": "B2B SaaS",
        "blurb": "Outbound + content + demos.",
        "growth_engine": "Trials driven by targeted content, comparison SEO, LinkedIn presence, and outreach.",
        "north_star": "Trials → paid conversion",
        "loop_metric": "CAC : LTV ratio",
        "metric_labels": {"north": "Trials", "loop": "Conversions", "visits": "Visits"},
        "channels": [
            {"name": "LinkedIn", "type": "repeatable", "target": "linkedin"},
            {"name": "SEO / comparison content", "type": "repeatable", "target": "article"},
            {"name": "Targeted communities", "type": "repeatable", "target": "reddit_opportunity"},
            {"name": "Cold outreach", "type": "repeatable", "target": None},
            {"name": "Webinars", "type": "one_shot", "target": None},
        ],
        "avoid": ["Reddit self-promo (gets nuked)", "TikTok", "mass Product Hunt reliance"],
    },
    "consumer": {
        "label": "Consumer app",
        "blurb": "Virality + influencer + app-store.",
        "growth_engine": "Installs from short-form virality, influencer seeding, and app-store discovery.",
        "north_star": "Installs → D1/D7 retention",
        "loop_metric": "K-factor + retention curve",
        "metric_labels": {"north": "Installs", "loop": "D7 retained", "visits": "Visits"},
        "channels": [
            {"name": "TikTok / IG / Reels", "type": "repeatable", "target": None},
            {"name": "Influencer seeding", "type": "repeatable", "target": None},
            {"name": "Product Hunt", "type": "one_shot", "target": None},
            {"name": "App-store optimization", "type": "repeatable", "target": None},
        ],
        "avoid": ["Hacker News (wrong crowd)", "long-form blog SEO early"],
    },
    "open_source": {
        "label": "Open source",
        "blurb": "Community + GitHub gravity.",
        "growth_engine": "Stars and contributors accrue from a Show HN moment, language/OSS communities, and GitHub trending.",
        "north_star": "Stars → contributors",
        "loop_metric": "Issues/PRs from outside",
        "metric_labels": {"north": "Stars", "loop": "Outside PRs", "visits": "Visits"},
        "channels": [
            {"name": "Show HN", "type": "one_shot", "target": "hn_post"},
            {"name": "Reddit (r/opensource, lang subs)", "type": "repeatable", "target": "reddit_reply"},
            {"name": "GitHub trending", "type": "repeatable", "target": None},
            {"name": "Discord", "type": "repeatable", "target": None},
            {"name": "Conference talks", "type": "one_shot", "target": None},
        ],
        "avoid": ["Paid ads", "'growth hacks'", "closed roadmap"],
    },
    "marketplace": {
        "label": "Marketplace / network",
        "blurb": "Seed the constrained side first.",
        "growth_engine": "Liquidity comes from manually seeding the supply side, then niche communities and targeted content.",
        "north_star": "Liquidity (match rate)",
        "loop_metric": "Repeat transactions",
        "metric_labels": {"north": "Matches", "loop": "Repeats", "visits": "Visits"},
        "channels": [
            {"name": "Manual supply seeding", "type": "repeatable", "target": None},
            {"name": "Niche communities", "type": "repeatable", "target": "reddit_opportunity"},
            {"name": "Targeted content", "type": "repeatable", "target": "article"},
        ],
        "avoid": ["Broad paid acquisition before liquidity exists"],
    },
}

UNIVERSAL_GUARDRAILS = [
    "No paid ads for a no-LTV product (free / one-time) — spend never recovers.",
    "No mass cross-posting the same link to many subreddits at once — shadowban.",
    "Never ask for upvotes on HN / Product Hunt — gets flagged.",
    "Don't buy followers or engagement — vanity, zero conversions.",
    "Don't fire all channels on Day 1 — wastes one-shots on an unproven funnel.",
    "Don't track retention on a one-time-use product — wrong yardstick.",
    "Never launch a share product with a broken OG unfurl — instant death.",
]


def _parse_json(raw: str) -> Any | None:
    """Tolerant JSON extraction — handles code fences + leading/trailing noise."""
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


# ---------------------------------------------------------------------------
# Shared system seed (Part 8.4)
# ---------------------------------------------------------------------------

LAUNCH_SYSTEM = """\
You are a launch strategist. Before any advice, classify the product into one
growth archetype. Everything you recommend — success metric, channels,
sequencing, what to avoid — must follow from that classification, not from
generic best practice. Be specific and opinionated. Kill channels that don't
fit (e.g. paid ads when there is no LTV). Never recommend firing one-shot
channels (Show HN, Product Hunt) on an unvalidated funnel. Always instrument
tracking before launch and tie every recommendation to ONE north-star metric.
State plainly when the founder's stated weakness (e.g. low follower count)
does not actually matter for their product type. No marketing fluff, no
em-dashes, no emojis.\
"""


# ---------------------------------------------------------------------------
# CLASSIFY
# ---------------------------------------------------------------------------

async def classify_product(
    llm: LLM, *, project: dict[str, Any], intake: dict[str, Any]
) -> dict[str, Any]:
    """Map the product to an archetype. Returns {archetype, confidence,
    reasoning, signals}. Human confirms before planning (one wrong call
    poisons everything)."""
    options = "\n".join(
        f"  - {key}: {a['label']} — {a['blurb']}" for key, a in ARCHETYPES.items()
    )
    system = (
        LAUNCH_SYSTEM
        + "\n\nClassify the product into exactly one archetype key. Output STRICT "
        "JSON only:\n"
        '{\n'
        '  "archetype": "<one of the keys>",\n'
        '  "confidence": "high|medium|low",\n'
        '  "reasoning": "<2-3 sentences on why this archetype, citing the product>",\n'
        '  "secondary": "<another key if it is a hybrid, else null>",\n'
        '  "watch_outs": ["<1-2 things the founder should know given this type>"]\n'
        "}\n\n"
        f"ARCHETYPE KEYS:\n{options}\n"
    )
    user = (
        f"PRODUCT: {project.get('name')}\n"
        f"URL: {project.get('url')}\n"
        f"DESCRIPTION: {project.get('description') or '(none)'}\n"
        f"COMPETITORS: {', '.join(project.get('competitors') or []) or '(none)'}\n"
        f"PRICING: {intake.get('pricing', '(unknown)')}\n"
        f"HAS RETENTION LOOP: {intake.get('has_retention_loop', '(unknown)')}\n"
        f"PRIMARY ARTIFACT: {intake.get('primary_artifact', '(none)')}\n"
        f"AUDIENCE: {intake.get('audience_who', '(unknown)')}\n\n"
        "Classify it now. Output only the JSON object."
    )
    raw = await llm.complete(
        [Message(role="system", content=system), Message(role="user", content=user)],
        temperature=0.3,
        max_tokens=700,
    )
    parsed = _parse_json(raw) or {}
    archetype = parsed.get("archetype")
    if archetype not in ARCHETYPES:
        # default to the safest generic read
        archetype = "dev_tool"
        parsed.setdefault("confidence", "low")
        parsed.setdefault("reasoning", "Could not confidently classify; defaulted. Please confirm or override.")
    parsed["archetype"] = archetype
    # attach the static archetype facts so the UI can render the derivation
    parsed["facts"] = _archetype_facts(archetype)
    return parsed


def _archetype_facts(key: str) -> dict[str, Any]:
    a = ARCHETYPES[key]
    return {
        "key": key,
        "label": a["label"],
        "growth_engine": a["growth_engine"],
        "north_star": a["north_star"],
        "loop_metric": a["loop_metric"],
        "channels": a["channels"],
        "avoid": a["avoid"],
    }


# ---------------------------------------------------------------------------
# PLAN
# ---------------------------------------------------------------------------

async def generate_launch_plan(
    llm: LLM,
    *,
    project: dict[str, Any],
    archetype: str,
    intake: dict[str, Any],
) -> dict[str, Any]:
    """Render the structured Week-1 launch plan for a confirmed archetype.

    The archetype fixes the channel order + metric names; the LLM customizes
    positioning, the channel rationale, and the per-day task lists.
    """
    if archetype not in ARCHETYPES:
        archetype = "dev_tool"
    a = ARCHETYPES[archetype]
    labels = a["metric_labels"]
    channel_order = ", ".join(c["name"] for c in a["channels"])

    system = (
        LAUNCH_SYSTEM
        + "\n\nProduce a Week-1 launch plan as STRICT JSON. The archetype is FIXED "
        "(given below) — do not re-classify. Customize positioning, the channel "
        "rationale, and the per-day task lists to THIS product. Tasks must be "
        "concrete and shippable in under 2 hours each. Lead Day 0 with a "
        "pre-launch gate (verify OG unfurl if it's a share product, verify the "
        "north-star event fires, confirm a cold visitor sees something alive).\n\n"
        "OUTPUT JSON SHAPE (no preface, no fences):\n"
        "{\n"
        '  "positioning": { "tagline": "...", "one_liner": "...", "share_hook": "..." },\n'
        '  "channels": [ { "name": "...", "type": "repeatable|one_shot", "day": <int>, "why": "..." } ],\n'
        '  "days": [\n'
        '    { "title": "Day 0 — Pre-launch gate", "channel": "prep", "gate": true,\n'
        '      "tasks": ["task", "task"] },\n'
        '    { "title": "Day 1 — ...", "channel": "...", "gate": false, "tasks": ["..."] }\n'
        "  ],\n"
        '  "decision_rules": ["if K high: ...", "if traffic high + conversion low: ...", "if quiet: ..."]\n'
        "}\n"
        "Produce Day 0 through Day 7 (8 day entries). Sequence channels by: "
        "forgiving-first, preserve one-shots (Show HN / Product Hunt come AFTER "
        "the funnel is proven), avoid crowd saturation."
    )
    user = (
        f"PRODUCT: {project.get('name')} ({project.get('url')})\n"
        f"DESCRIPTION: {project.get('description') or '(none)'}\n"
        f"COMPETITORS: {', '.join(project.get('competitors') or []) or '(none)'}\n\n"
        f"ARCHETYPE (fixed): {a['label']}\n"
        f"GROWTH ENGINE: {a['growth_engine']}\n"
        f"NORTH-STAR: {a['north_star']}\n"
        f"LOOP METRIC: {a['loop_metric']}\n"
        f"CHANNEL ORDER (use this sequence): {channel_order}\n"
        f"AVOID: {', '.join(a['avoid'])}\n\n"
        f"INTAKE:\n"
        f"  pricing: {intake.get('pricing', '(unknown)')}\n"
        f"  has_retention_loop: {intake.get('has_retention_loop', '(unknown)')}\n"
        f"  primary_artifact: {intake.get('primary_artifact', '(none)')}\n"
        f"  audience: {intake.get('audience_who', '(unknown)')}\n"
        f"  founder_can_produce: {intake.get('founder_can_produce', '(unknown)')}\n"
        f"  founder_reach: {intake.get('founder_reach', '(unknown)')}\n"
        f"  budget: {intake.get('budget', '0')}\n"
        f"  og_unfurl_works: {intake.get('og_unfurl_works', '(unknown)')}\n\n"
        "Generate the plan now. Output only the JSON object."
    )
    raw = await llm.complete(
        [Message(role="system", content=system), Message(role="user", content=user)],
        temperature=0.6,
        max_tokens=3000,
    )
    parsed = _parse_json(raw) or {}

    # Normalize days into the tracker shape (tasks → {text, done}, metrics seeded)
    days_in = parsed.get("days") or []
    days: list[dict[str, Any]] = []
    for d in days_in:
        if not isinstance(d, dict):
            continue
        tasks = []
        for t in d.get("tasks") or []:
            if isinstance(t, str):
                tasks.append({"text": t, "done": False})
            elif isinstance(t, dict) and t.get("text"):
                tasks.append({"text": t["text"], "done": bool(t.get("done"))})
        days.append({
            "title": str(d.get("title") or "Day"),
            "channel": str(d.get("channel") or ""),
            "gate": bool(d.get("gate")),
            "tasks": tasks,
            "metrics": {"visits": "", "north": "", "loop": "", "referrer": ""},
        })
    if not days:
        days = _fallback_days(a)

    # attach archetype targets onto channels for the ASSETS phase; fall back
    # to the archetype table when the model omits channels entirely
    target_by_name = {c["name"]: c.get("target") for c in a["channels"]}
    channels = parsed.get("channels") or []
    if not channels:
        channels = [
            {"name": c["name"], "type": c["type"], "day": i + 1, "why": a["growth_engine"]}
            for i, c in enumerate(a["channels"])
        ]
    for c in channels:
        if isinstance(c, dict):
            c["target"] = target_by_name.get(c.get("name"))

    # positioning fallback seeded from the project
    positioning = parsed.get("positioning") or {}
    if not positioning.get("one_liner"):
        positioning.setdefault("tagline", project.get("name") or "")
        positioning.setdefault("one_liner", project.get("description") or "")
        positioning.setdefault("share_hook", "")

    plan = {
        "classification": archetype,
        "archetype_label": a["label"],
        "growth_engine": a["growth_engine"],
        "positioning": positioning,
        "metrics": {
            "north": labels["north"],
            "loop": labels["loop"],
            "visits": labels["visits"],
            "north_star_desc": a["north_star"],
            "loop_desc": a["loop_metric"],
        },
        "channels": channels,
        "days": days,
        "decision_rules": parsed.get("decision_rules") or _default_decision_rules(labels),
        "guardrails": UNIVERSAL_GUARDRAILS,
    }
    return plan


def _default_decision_rules(labels: dict[str, str]) -> list[str]:
    n, lo, v = labels["north"], labels["loop"], labels["visits"]
    return [
        f"If K ({lo}÷{n}) is high and self-sustaining: keep cadence on the winning channel, reduce manual push.",
        f"If {v} are high but {n} conversion is low: do NOT push more traffic, fix the landing→action handoff first.",
        "If all channels are quiet: pivot from push to pull, publish SEO/comparison content and let search/LLM citation accrue.",
        "Otherwise: repeat the best repeatable channel; only re-test a one-shot with a materially new angle.",
    ]


def _fallback_days(a: dict[str, Any]) -> list[dict[str, Any]]:
    """Minimal Week-1 skeleton if the LLM plan parse fails."""
    chans = a["channels"]
    base = [
        {"title": "Day 0 — Pre-launch gate", "channel": "prep", "gate": True,
         "tasks": [
             "Verify the product works end-to-end on mobile",
             "Confirm the north-star event fires in analytics",
             "Confirm a cold visitor sees something alive",
             "Build UTM links, one per channel",
         ]},
    ]
    for i, c in enumerate(chans[:7], start=1):
        base.append({
            "title": f"Day {i} — {c['name']}",
            "channel": c["name"],
            "gate": False,
            "tasks": [f"Post to {c['name']} with the UTM link", "Reply to every comment within 3h"],
        })
    for d in base:
        d.setdefault("metrics", {"visits": "", "north": "", "loop": "", "referrer": ""})
        d["tasks"] = [{"text": t, "done": False} for t in d["tasks"]]
    return base


# ---------------------------------------------------------------------------
# TRACK — daily decision loop
# ---------------------------------------------------------------------------

def compute_scoreboard(plan: dict[str, Any]) -> dict[str, Any]:
    """Roll up the tracker math (totals, K, funnel%, task completion) from the
    plan's day metrics. Pure function — no LLM."""
    tot_n = tot_l = tot_v = 0.0
    done = total = 0
    for d in plan.get("days") or []:
        m = d.get("metrics") or {}
        tot_n += _num(m.get("north"))
        tot_l += _num(m.get("loop"))
        tot_v += _num(m.get("visits"))
        for t in d.get("tasks") or []:
            total += 1
            if isinstance(t, dict) and t.get("done"):
                done += 1
    k = (tot_l / tot_n) if tot_n else 0.0
    funnel = (tot_n / tot_v * 100) if tot_v else 0.0
    return {
        "total_north": tot_n,
        "total_loop": tot_l,
        "total_visits": tot_v,
        "k": round(k, 2),
        "funnel_pct": round(funnel, 1),
        "tasks_done": done,
        "tasks_total": total,
        "tasks_pct": round(done / total * 100) if total else 0,
    }


def _num(v: Any) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


async def launch_track_advice(
    llm: LLM, *, plan: dict[str, Any], scoreboard: dict[str, Any]
) -> dict[str, Any]:
    """Apply the decision rules to the current scoreboard → 'today's move'."""
    metrics = plan.get("metrics") or {}
    system = (
        LAUNCH_SYSTEM
        + "\n\nGiven the launch's current numbers and its decision rules, output "
        "the single most important move for today. STRICT JSON:\n"
        '{ "move": "<one concrete action>", "rationale": "<one sentence>", '
        '"rule_fired": "<which decision rule applies>" }\n'
        "Be decisive. One move, not a list."
    )
    user = (
        f"NORTH-STAR: {metrics.get('north_star_desc')}\n"
        f"DECISION RULES:\n" + "\n".join(f"  - {r}" for r in plan.get("decision_rules") or []) + "\n\n"
        f"CURRENT NUMBERS:\n"
        f"  total {metrics.get('north')}: {scoreboard['total_north']}\n"
        f"  K ({metrics.get('loop')}÷{metrics.get('north')}): {scoreboard['k']}\n"
        f"  funnel %: {scoreboard['funnel_pct']}\n"
        f"  visits: {scoreboard['total_visits']}\n"
        f"  tasks done: {scoreboard['tasks_done']}/{scoreboard['tasks_total']}\n\n"
        "What's today's move? Output only the JSON object."
    )
    raw = await llm.complete(
        [Message(role="system", content=system), Message(role="user", content=user)],
        temperature=0.4,
        max_tokens=400,
    )
    parsed = _parse_json(raw) or {}
    return {
        "move": str(parsed.get("move") or "Keep momentum on your strongest channel and fill tonight's scorecard."),
        "rationale": str(parsed.get("rationale") or ""),
        "rule_fired": str(parsed.get("rule_fired") or ""),
        "scoreboard": scoreboard,
    }


def default_intake(project: dict[str, Any]) -> dict[str, Any]:
    """Seed the intake form from what the project already knows."""
    return {
        "one_liner": project.get("description") or "",
        "pricing": "",
        "has_retention_loop": None,
        "primary_artifact": "",
        "audience_who": "",
        "founder_can_produce": [],
        "founder_reach": "",
        "budget": "0",
        "og_unfurl_works": None,
        "goal": "",
        "launch_date": "",
    }
