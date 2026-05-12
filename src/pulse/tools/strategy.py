"""Strategy tools — brand voice extraction, marketing plan generation, etc."""

from __future__ import annotations

import json
import re

import structlog

from ..llm import LLM, Message
from ..store import ActionStore
from .registry import Tool, tool

log = structlog.get_logger()


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return text


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
        raw = _strip_code_fence(raw)
        try:
            profile = json.loads(raw)
        except json.JSONDecodeError:
            return json.dumps({"ok": False, "error": "could not parse voice profile", "raw": raw[:500]})

        profile["samples"] = [s.strip() for s in writing_samples[:3] if s.strip()]
        store.set_brand_voice(project_id, profile)
        return json.dumps({"ok": True, "profile": profile})

    @tool
    async def generate_marketing_strategy(timeframe_days: int = 30) -> str:
        """Generate a marketing strategy for the next N days.

        Uses everything the agent has learned this run (product info, SEO state,
        competitors) to output a concrete 30/60/90 day plan. Saved as an action.

        Args:
            timeframe_days: 30, 60, or 90.
        """
        if timeframe_days not in (30, 60, 90):
            timeframe_days = 30
        project = store.get_project(project_id)
        if project is None:
            return json.dumps({"ok": False, "error": "project not found"})

        system = (
            "You are a marketing strategist for indie founders. Output a concrete, "
            "no-fluff plan in markdown. Use H2 sections for each phase. Every "
            "bullet should be something the founder can ship in <2 hours. No "
            "'leverage synergies' nonsense. Specifics > frameworks."
        )
        user = (
            f"product: {project.get('name')} ({project.get('url')})\n"
            f"description: {project.get('description') or '(none)'}\n"
            f"competitors: {', '.join(project.get('competitors') or []) or '(none known)'}\n"
            f"timeframe: next {timeframe_days} days\n\n"
            "Write the plan."
        )
        plan = await llm.complete(
            [Message(role="system", content=system), Message(role="user", content=user)],
            temperature=0.55,
            max_tokens=2000,
        )
        # Save under last run id (fetch most recent run for project)
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
    async def identify_market_gaps(competitor_summaries: list[str]) -> str:
        """Identify positioning gaps the user can exploit vs their competitors.

        Pass 2-5 short summaries of competitor positioning (after analyze_competitor).
        Returns 3-5 concrete gap opportunities the user could lean into, each saved
        as a 'market_gap' action.

        Args:
            competitor_summaries: List of competitor positioning summaries (1-2 sentences each).
        """
        if not competitor_summaries:
            return json.dumps({"ok": False, "error": "competitor_summaries required"})
        project = store.get_project(project_id)
        if not project:
            return json.dumps({"ok": False, "error": "project not found"})

        comp_block = "\n".join(f"- {s.strip()}" for s in competitor_summaries[:6] if s.strip())
        system = (
            "You analyze competitive positioning and surface unclaimed angles. "
            "Output STRICT JSON ONLY in this shape:\n"
            "{\"gaps\": [\n"
            "  {\"title\": \"<short title, max 80 chars>\",\n"
            "   \"opportunity\": \"<2-3 sentences on the gap + why we can win it>\",\n"
            "   \"first_move\": \"<concrete first thing to ship>\"}\n"
            "]}\n"
            "Aim for 3-5 gaps. Be sharp — generic gaps like 'better UX' don't count. "
            "Look at pricing posture, audience segments, distribution channels, "
            "missing features, ideological positioning. Output JSON only."
        )
        user = (
            f"Product: {project.get('name')} ({project.get('url')})\n"
            f"About: {project.get('description') or '(unknown)'}\n\n"
            f"Competitors:\n{comp_block}\n\n"
            "Find the gaps."
        )
        raw = await llm.complete(
            [Message(role="system", content=system), Message(role="user", content=user)],
            temperature=0.55,
            max_tokens=1200,
        )
        raw = _strip_code_fence(raw)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
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

    return [extract_brand_voice, generate_marketing_strategy, update_project_info, identify_market_gaps]
