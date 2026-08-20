"""Strategy tools — brand voice extraction, marketing plan generation, etc."""

from __future__ import annotations

import json

import structlog

from ..llm import LLM, Message
from ..store import ActionStore
from ..strategy_core import (
    ANALYST_STYLE,
    GUARDRAIL_BLOCK,
    critique_revise,
    gather_evidence,
    generate_channel_bet,
    generate_positioning,
    generate_weekly_plan,
    render_evidence,
    render_gtm_plan_doc,
)
from ..text import parse_json_lenient, strip_stray_cjk
from .registry import Tool, tool

log = structlog.get_logger()


def make_strategy_tools(llm: LLM, store: ActionStore, project_id: int) -> list[Tool]:

    @tool
    async def extract_brand_voice(writing_samples: list[str]) -> str:
        """Analyze writing samples to extract a brand voice profile.

        Pass 1-5 writing samples (blog posts, tweets, about pages, etc) and
        get back a structured voice profile that drafting tools use to mimic
        the user's voice. The profile is persisted on the project.

        Args:
            writing_samples: List of 1-5 text samples (each up to a few paragraphs).
        """
        if not writing_samples:
            return json.dumps({"ok": False, "error": "no writing samples provided"})
        samples_block = "\n\n---\n\n".join(s.strip() for s in writing_samples[:5] if s.strip())
        if not samples_block:
            return json.dumps({"ok": False, "error": "all samples were empty"})

        system = (
            "You analyze writing samples and produce a structured voice profile. "
            "Output ONLY valid JSON in this shape:\n"
            "{\n"
            '  "tone": "<2-4 word summary, e.g. \'direct, witty, builder\'>",\n'
            '  "vocabulary": "<a few signature words or phrases the author uses>",\n'
            '  "rhythm": "<short note on sentence structure>",\n'
            '  "taboo": ["word1","word2"]\n'
            "}\n"
            "Do not include the writing samples themselves. Output JSON only, no preface."
        )
        user = "writing samples:\n\n" + samples_block

        raw = await llm.complete(
            [Message(role="system", content=system), Message(role="user", content=user)],
            temperature=0.3,
            max_tokens=600,
        )
        profile = parse_json_lenient(raw)
        if not isinstance(profile, dict):
            return json.dumps({"ok": False, "error": "could not parse voice profile", "raw": raw[:500]})

        profile["samples"] = [s.strip() for s in writing_samples[:3] if s.strip()]
        store.set_brand_voice(project_id, profile)
        return json.dumps({"ok": True, "profile": profile})

    @tool
    async def build_product_brain() -> str:
        """Build the Product Brain — the shared intelligence (the WEDGE, ICP,
        JTBD, the ICP's exact vocabulary, target communities, and intent-grouped
        search queries) that EVERY later step conditions on for relevance.

        Call this on the first dive AFTER the crawl + 1-2 `analyze_competitor`
        calls and BEFORE positioning / strategy / content / discovery. Reads the
        persisted evidence itself; no arguments.
        """
        from ..product_brain import generate_product_brain

        brain = await generate_product_brain(llm, store, project_id)
        if not brain:
            return json.dumps({"ok": False, "error": "could not build product brain"})
        return json.dumps({
            "ok": True,
            "wedge": (brain.get("wedge") or {}).get("capability", ""),
            "icp_vocabulary": (brain.get("icp_vocabulary") or [])[:6],
            "target_subreddits": (brain.get("communities") or {}).get("subreddits", [])[:6],
        })

    @tool
    async def generate_positioning_doc() -> str:
        """Run the strategic diagnosis (situation, ICP, value prop, the wedge,
        ranked channels with leading indicators, measurement, open questions).

        Call this on the first dive AFTER the crawl + brand voice + audits +
        (ideally) one or two `analyze_competitor` calls, and BEFORE
        `generate_marketing_strategy` — the strategy is built on this. It reads
        the persisted evidence itself; no arguments needed. Saves the
        'positioning' document.
        """
        pos = await generate_positioning(llm, store, project_id)
        if not pos:
            return json.dumps({"ok": False, "error": "could not produce positioning"})
        wedge = (pos.get("wedge") or {}).get("move", "")
        return json.dumps({"ok": True, "wedge": wedge, "value_prop": pos.get("value_prop", "")})

    @tool
    async def commit_channel_bet() -> str:
        """Commit the ONE channel bet and open week 1 of the GTM loop.

        Call this on the first dive AFTER build_product_brain and
        generate_positioning_doc. It picks the single highest-fit channel (not a
        ranked list), defines the play (the repeatable asset, cadence, exact
        targets), the leading indicator, and the kill criteria — then generates
        this week's 3 concrete moves. Concentration beats spray at 0->1. Reads the
        persisted evidence itself; no arguments. Saves the 'gtm_plan' document.
        """
        bet = await generate_channel_bet(llm, store, project_id)
        if not bet:
            return json.dumps({"ok": False, "error": "could not commit a channel bet"})
        week = await generate_weekly_plan(llm, store, project_id)
        render_gtm_plan_doc(store, project_id)
        moves = [
            (m.get("move") or "")[:90]
            for m in ((week or {}).get("plan") or {}).get("moves", [])
        ]
        return json.dumps({
            "ok": True,
            "channel": bet.get("channel", ""),
            "play_asset": (bet.get("play") or {}).get("asset", ""),
            "leading_indicator": bet.get("leading_indicator", ""),
            "week_moves": moves,
        })

    @tool
    async def generate_marketing_strategy(timeframe_days: int = 30) -> str:
        """Generate an evidence-grounded marketing plan for the next N days.

        Reads everything gathered this run — the crawl, the founder's brief
        (goal / ICP / baseline / constraints), the positioning diagnosis, SEO +
        traction state, and the REAL competitor reads — and turns the wedge into
        a sequenced plan tied to the founder's actual goal, with a leading
        indicator on every item. If positioning hasn't been diagnosed yet it
        does that first. Saved as an action.

        Args:
            timeframe_days: 30, 60, or 90.
        """
        if timeframe_days not in (30, 60, 90):
            timeframe_days = 30
        project = store.get_project(project_id)
        if project is None:
            return json.dumps({"ok": False, "error": "project not found"})

        ev = gather_evidence(store, project_id)
        # The plan is only as good as its diagnosis — ensure one exists.
        if not ev.get("positioning"):
            await generate_positioning(llm, store, project_id)
            ev = gather_evidence(store, project_id)

        evidence_block = render_evidence(
            ev, include=("brain", "product", "brief", "positioning", "seo", "traction", "competitors")
        )
        system = (
            "You are a head of growth writing the next-"
            f"{timeframe_days}-day marketing plan for an indie founder. You have a "
            "positioning diagnosis, the founder's brief, and real evidence. Turn "
            "the wedge into a sequenced plan — not a generic channel checklist.\n\n"
            + ANALYST_STYLE
            + "\n\n"
            + GUARDRAIL_BLOCK
            + "\n\nOUTPUT (markdown):\n"
            "- 2-3 lines: the situation and the ONE bet this plan makes (the wedge).\n"
            "- An H2 per phase (Week 1, Week 2, ...). Every bullet is a concrete "
            "action shippable in under 2 hours, and ends with, in italics, the "
            "leading indicator it should move + the channel. No vague "
            "'engage the community'.\n"
            "- End with one or two 'if X then Y' decision rules and an explicit "
            "'stop doing' line.\n"
            "Tie the plan to the brief's goal and success metric. If the founder "
            "gave a baseline, the plan must visibly try to move it. Never propose "
            "anything they said already flopped."
        )
        user = evidence_block + f"\n\nTIMEFRAME: next {timeframe_days} days.\n\nWrite the plan."
        plan = await llm.complete(
            [Message(role="system", content=system), Message(role="user", content=user)],
            temperature=0.5,
            max_tokens=20000,
            fallback_to_reasoning=True,
        )
        # generate -> verify -> revise: a separate critic rewrites generic/off-wedge
        # lines and strips any meta-narration ("Let me analyze…") before saving.
        plan = await critique_revise(
            llm, kind="30-day marketing plan", draft=plan, brain=ev.get("brain")
        )
        if not plan.strip():
            return json.dumps({"ok": False, "error": "marketing strategy generation returned empty content"})
        run_id = store.latest_run_id(project_id)
        action_id = store.create_action(
            project_id=project_id,
            run_id=run_id or 0,
            action_type="strategy",
            title=f"{timeframe_days}-day marketing strategy",
            content=plan.strip(),
            context={"timeframe_days": timeframe_days},
        )
        return json.dumps({"ok": True, "action_id": action_id, "preview": plan[:500]})

    @tool
    async def update_project_info(name: str = "", description: str = "", competitors: list[str] = []) -> str:
        """Update what the agent knows about the project.

        Pass only the fields you want to change. Use after crawl_website to
        persist the product description, name, and competitor list you inferred.

        Args:
            name: Product name.
            description: Short product description (1-3 sentences).
            competitors: List of competitor URLs or names.
        """
        updates: dict = {}
        if name:
            updates["name"] = name
        if description:
            updates["description"] = description
        if competitors:
            updates["competitors"] = competitors
        if not updates:
            return json.dumps({"ok": False, "error": "no fields to update"})
        store.update_project(project_id, **updates)
        return json.dumps({"ok": True, "updated": list(updates.keys())})

    @tool
    async def identify_market_gaps(competitor_summaries: list[str] = []) -> str:
        """Identify positioning gaps the user can exploit vs their competitors.

        Uses the REAL competitor reads Pulse crawled (via analyze_competitor) and
        the positioning diagnosis — you don't need to pass anything. Optionally
        pass extra one-line competitor notes to fold in. Returns 3-5 concrete gap
        opportunities, each saved as a 'market_gap' action.

        Args:
            competitor_summaries: Optional extra competitor notes (1-2 sentences each).
        """
        project = store.get_project(project_id)
        if not project:
            return json.dumps({"ok": False, "error": "project not found"})

        ev = gather_evidence(store, project_id)
        evidence_block = render_evidence(
            ev, include=("brain", "product", "brief", "positioning", "competitors")
        )
        extra = "\n".join(f"- {s.strip()}" for s in (competitor_summaries or [])[:6] if s.strip())
        if not ev.get("competitor_reads") and not extra:
            return json.dumps({"ok": False, "error": "no competitor evidence — run analyze_competitor first"})
        if extra:
            evidence_block += f"\n\nADDITIONAL COMPETITOR NOTES:\n{extra}"

        system = (
            "You analyze competitive positioning and surface unclaimed angles, "
            "grounded in the crawled competitor evidence.\n\n"
            + ANALYST_STYLE
            + "\n\nOutput STRICT JSON ONLY in this shape:\n"
            "{\"gaps\": [\n"
            "  {\"title\": \"<short title, max 80 chars>\",\n"
            "   \"opportunity\": \"<2-3 sentences on the gap + why THIS product can win it, citing the evidence>\",\n"
            "   \"first_move\": \"<concrete first thing to ship>\"}\n"
            "]}\n"
            "Aim for 3-5 gaps. Be sharp — generic gaps like 'better UX' don't count. "
            "Look at pricing posture, audience segments, distribution channels, "
            "missing features, ideological positioning. Output JSON only."
        )
        user = evidence_block + "\n\nFind the gaps. Output only the JSON object."
        raw = await llm.complete(
            [Message(role="system", content=system), Message(role="user", content=user)],
            temperature=0.5,
            max_tokens=1300,
        )
        parsed = parse_json_lenient(raw)
        if not isinstance(parsed, dict):
            return json.dumps({"ok": False, "error": "could not parse JSON", "raw": raw[:400]})

        gaps = parsed.get("gaps") or []
        run_id = store.latest_run_id(project_id) or 0
        action_ids: list[int] = []
        for g in gaps[:5]:
            title = (g.get("title") or "")[:120].strip()
            opp = (g.get("opportunity") or "").strip()
            move = (g.get("first_move") or "").strip()
            if not title or not opp:
                continue
            body = f"**Opportunity:** {opp}\n\n**First move:** {move}" if move else f"**Opportunity:** {opp}"
            aid = store.create_action(
                project_id=project_id,
                run_id=run_id,
                action_type="market_gap",
                title=title,
                content=body,
                context={"opportunity": opp, "first_move": move},
            )
            action_ids.append(aid)
        return json.dumps({"ok": True, "action_ids": action_ids, "gaps_found": len(action_ids)})

    return [
        extract_brand_voice,
        build_product_brain,
        generate_positioning_doc,
        commit_channel_bet,
        generate_marketing_strategy,
        update_project_info,
        identify_market_gaps,
    ]
