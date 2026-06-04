"""Run orchestrator — composes tools + system prompt for each run kind.

Run kinds:
  * first_dive    — initial dive: diagnose the product, sharpen the message,
                    commit ONE channel bet, open week 1. (agent loop)
  * weekly        — scheduled lean refresh: roll the GTM week forward when stale.
                    No firehose, no snapshot needed. (deterministic)
  * weekly_review — founder-triggered: read the week's real numbers, make the
                    call, replan next week. (deterministic)
  * manual        — user-initiated ad-hoc run with a custom instruction.
  * targeted      — generate ONE asset of a specific kind for the "+" buttons.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import structlog

from .agent import Agent
from .config import Config
from .llm import LLM
from .store import ActionStore
from .strategy_core import (
    generate_weekly_plan,
    render_gtm_plan_doc,
    run_weekly_review as _run_weekly_review_core,
)
from .tools import ToolRegistry
from .tools.crawl import make_crawl_tools
from .tools.discovery import make_discovery_tools
from .tools.documents import make_document_tools
from .tools.drafting import make_drafting_tools
from .tools.reddit import make_reddit_tools
from .tools.seo import make_seo_tools
from .tools.strategy import make_strategy_tools
from .tools.web import make_web_tools

log = structlog.get_logger()


FIRST_DIVE_PROMPT = """\
You are Pulse — an AI GTM operator for indie founders. This is the first dive on
a new project: the founder just gave you their site URL.

Your job is NOT to spray content. It is to start ONE disciplined GTM loop:
understand the product, sharpen the message, commit to a SINGLE channel bet, and
lay out this week's first moves. A sharp bet beats a pile of generic posts. If a
MARKETING BRIEF is in the context below, every output serves the founder's stated
goal, ICP, and constraints.

EXECUTE IN ORDER. Steps 7-9 (brain -> positioning -> the bet) are the whole point.

1. CRAWL with `crawl_website` (max_pages=10). Extract product, audience, pricing,
   tone. If the URL is a GitHub repo, use the returned repo metadata (stars,
   language, topics) + README as the product picture, and if it has a `homepage`,
   treat THAT as the site.

2. CALL `update_project_info` with name, description, and any competitors spotted.

3. EXTRACT brand voice with `extract_brand_voice` using homepage hero + about +
   any blog excerpts as writing_samples.

4. CALL `generate_product_information` to save the Product Information document.

5. SEO HYGIENE — ONE `audit_seo` on the homepage (for a repo, its `homepage` URL;
   skip if it has none). Log only HIGH findings with `log_seo_fix`. This is a
   one-time hygiene pass, not a channel — do not re-audit and do not chase low/
   medium nits.

6. RESEARCH COMPETITORS: for the top 1-2, `analyze_competitor` on each URL (use
   `web_search` if you don't know it). Reads are saved automatically. Cap at 2.

7. BUILD THE PRODUCT BRAIN: `build_product_brain` (no arguments). Distills the
   crawl + brief + competitor reads into the WEDGE, the ICP and their exact
   vocabulary, and the communities they live in. Everything below conditions on
   it, so output is specific to THIS product. Do this before positioning.

8. DIAGNOSE: `generate_positioning_doc` (no arguments) — situation, ICP, value
   prop, the WEDGE, ranked channels, north-star metric. The message spine.

9. COMMIT THE BET: `commit_channel_bet` (no arguments). Picks the ONE highest-fit
   channel (not a ranked list), the play (asset / cadence / exact targets), the
   leading indicator, and the kill criteria — then opens this week's 3 moves.
   THIS is the core deliverable of the dive.

10. MAKE THE FIRST ASSET — exactly one, on-wedge, serving the bet:
    - If the bet's play is content or SEO: call `news_search`/`web_search` for
      3-5 recent items (dates + sources), then `draft_article` (length=800)
      passing them as `current_context`.
    - Otherwise: `draft_tweet` introducing the product on the wedge. one tweet.
    Pick the ONE that fits the bet's play. Do not draft several.

STOP when done. Output a 3-5 line summary: the wedge, the channel bet, and this
week's 3 moves.

RULES:
  * Use tools — don't speculate. Each call should be motivated by a result.
  * NEVER call the same tool more than once unless explicitly told to.
  * Anchor EVERY output on the brain's wedge + ICP vocabulary. If a suggestion
    would apply to any product, it's wrong — make it specific.
  * Steps 7-9 (brain, positioning, the bet) MUST complete — they are the dive.
    Step 10 is the only one to drop if you run low on iterations.
"""


def build_registry_for_run(
    config: Config,
    llm: LLM,
    store: ActionStore,
    project_id: int,
    run_id: int,
) -> ToolRegistry:
    """Build a tool registry scoped to a specific run."""
    registry = ToolRegistry()
    for t in make_web_tools(
        base_url=config.web.base_url,
        api_key=config.web_api_key(),
        timeout=config.web.timeout,
    ):
        registry.add(t)
    try:
        _web_key = config.web_api_key()
    except Exception:
        _web_key = ""
    for t in make_crawl_tools(
        store, project_id, web_base_url=config.web.base_url, web_api_key=_web_key
    ):
        registry.add(t)
    for t in make_seo_tools(store=store, project_id=project_id):
        registry.add(t)
    for t in make_discovery_tools(store, project_id, llm):
        registry.add(t)
    for t in make_drafting_tools(llm=llm, store=store, project_id=project_id, run_id=run_id):
        registry.add(t)
    for t in make_strategy_tools(llm=llm, store=store, project_id=project_id):
        registry.add(t)
    for t in make_document_tools(llm=llm, store=store, project_id=project_id):
        registry.add(t)
    for t in make_reddit_tools(
        llm=llm, store=store, project_id=project_id, run_id=run_id,
        web_base_url=config.web.base_url, web_api_key=_web_key,
    ):
        registry.add(t)
    return registry


def _project_context(project: dict[str, Any]) -> str:
    from .brief import brief_context_block

    bv = project.get("brand_voice")
    bv_block = ""
    if bv:
        bv_block = f"\nbrand voice tone: {bv.get('tone', '')}\nbrand voice taboo: {', '.join(bv.get('taboo') or [])}"
    brief_block = brief_context_block(project.get("brief"))
    brief_block = ("\n\n" + brief_block) if brief_block else ""
    return (
        f"PROJECT CONTEXT:\n"
        f"name: {project.get('name')}\n"
        f"url: {project.get('url')}\n"
        f"description: {project.get('description') or '(not yet inferred)'}\n"
        f"competitors: {', '.join(project.get('competitors') or []) or '(none known)'}"
        f"{bv_block}"
        f"{brief_block}"
    )


async def run_first_dive(
    *,
    config: Config,
    llm: LLM,
    store: ActionStore,
    project_id: int,
    run_id: int,
) -> AsyncIterator[dict[str, Any]]:
    project = store.get_project(project_id)
    if not project:
        raise ValueError(f"project {project_id} not found")
    registry = build_registry_for_run(config, llm, store, project_id, run_id)
    agent = Agent(
        llm=llm,
        registry=registry,
        system_prompt=FIRST_DIVE_PROMPT + "\n\n" + _project_context(project),
        max_iterations=config.agent.max_iterations,
    )
    user_msg = {
        "role": "user",
        "content": f"Begin the first dive on {project['url']}. Follow the steps in order.",
    }
    async for ev in agent.stream([user_msg]):
        yield ev


def _week_is_stale(week: dict[str, Any] | None, *, days: int = 7) -> bool:
    """True if the current week's plan is old enough to roll forward."""
    if not week:
        return True
    try:
        started = datetime.fromisoformat(str(week.get("started_at")))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - started).days >= days
    except (ValueError, TypeError):
        return True


async def run_weekly(
    *,
    config: Config,
    llm: LLM,
    store: ActionStore,
    project_id: int,
    run_id: int,
) -> AsyncIterator[dict[str, Any]]:
    """Scheduled lean refresh: roll this week's 3 moves forward when the current
    plan is stale (>= 7 days). No firehose, no channels spammed, no snapshot
    needed — just keep the plan current. Deterministic; safe to fire daily (it
    no-ops until a week has passed)."""
    project = store.get_project(project_id)
    if not project:
        raise ValueError(f"project {project_id} not found")

    yield {"type": "start"}
    yield {"type": "iteration", "n": 1}

    if not store.get_channel_bet(project_id):
        msg = "No channel bet committed yet — run the first dive first."
        yield {"type": "text", "text": msg}
        yield {"type": "done", "iterations": 1, "content": msg}
        return

    week = store.current_gtm_week(project_id)
    if week and not _week_is_stale(week):
        msg = f"This week's plan is still fresh (week {week.get('week_num')}). Nothing to refresh."
        yield {"type": "text", "text": msg}
        yield {"type": "done", "iterations": 1, "content": msg}
        return

    yield {"type": "text", "text": "Rolling the GTM week forward — refreshing this week's 3 moves.\n"}
    prior_review = (week or {}).get("review")
    new_week = await generate_weekly_plan(llm, store, project_id, prior_review=prior_review)
    render_gtm_plan_doc(store, project_id)
    if not new_week:
        msg = "Could not refresh the plan this time."
        yield {"type": "text", "text": msg}
        yield {"type": "done", "iterations": 1, "content": msg}
        return
    moves = [m.get("move", "") for m in (new_week.get("plan") or {}).get("moves", [])]
    summary = f"Week {new_week.get('week_num')} plan:\n" + "\n".join(f"- {m}" for m in moves)
    yield {"type": "text", "text": summary}
    yield {"type": "done", "iterations": 1, "content": summary}


async def run_weekly_review(
    *,
    config: Config,
    llm: LLM,
    store: ActionStore,
    project_id: int,
    run_id: int,
    instruction: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """Founder-triggered: read the week's real numbers (the snapshot arrives as
    JSON in `instruction`) against the plan, make the call (continue / adjust /
    kill), re-bet on a kill, and open next week's plan. Deterministic — no agent
    fan-out, no generic output."""
    project = store.get_project(project_id)
    if not project:
        raise ValueError(f"project {project_id} not found")

    try:
        snapshot = json.loads(instruction) if instruction.strip() else {}
    except json.JSONDecodeError:
        snapshot = {"notes": instruction}
    if not isinstance(snapshot, dict):
        snapshot = {"notes": str(snapshot)}

    yield {"type": "start"}
    yield {"type": "iteration", "n": 1}
    yield {"type": "text", "text": "Reading your week against the plan and making the call.\n"}

    result = await _run_weekly_review_core(llm, store, project_id, snapshot)
    review = result.get("review") or {}
    next_week = result.get("week") or {}

    lines: list[str] = []
    if review.get("the_call"):
        lines.append(f"The call ({review.get('call_kind', '')}): {review.get('the_call')}")
        lines.append("")
    moves = [m.get("move", "") for m in (next_week.get("plan") or {}).get("moves", [])]
    if moves:
        lines.append(f"Next week (week {next_week.get('week_num')}):")
        lines += [f"- {m}" for m in moves]
    summary = "\n".join(lines) or "Weekly review complete."
    yield {"type": "text", "text": summary}
    yield {"type": "done", "iterations": 1, "content": summary}


async def run_manual(
    *,
    config: Config,
    llm: LLM,
    store: ActionStore,
    project_id: int,
    run_id: int,
    instruction: str,
) -> AsyncIterator[dict[str, Any]]:
    project = store.get_project(project_id)
    if not project:
        raise ValueError(f"project {project_id} not found")
    registry = build_registry_for_run(config, llm, store, project_id, run_id)
    system = (
        "You are Pulse — an AI marketing operator. The user is asking you to "
        "perform a specific task. Use the available tools when appropriate. "
        "Be concise and concrete.\n\n"
        + _project_context(project)
    )
    agent = Agent(
        llm=llm,
        registry=registry,
        system_prompt=system,
        max_iterations=config.agent.max_iterations,
    )
    async for ev in agent.stream([{"role": "user", "content": instruction}]):
        yield ev


# ---------------------------------------------------------------------------
# Targeted runs — generate ONE action of a specific kind, fast.
# ---------------------------------------------------------------------------

# Per-target playbook. Each entry produces a focused system prompt + max iter
# budget for that channel. The agent only runs the steps it needs; the topic
# argument is appended verbatim into the user message.
_TARGET_PLAYBOOK: dict[str, dict[str, Any]] = {
    "tweet": {
        "label": "tweet",
        "max_iter": 4,
        "steps": (
            "1. (Optional, if topic mentions a current event) call `news_search`\n"
            "   for ONE timely angle.\n"
            "2. Call `draft_tweet` with the topic. ONE draft. Three variants will\n"
            "   be saved automatically.\n"
            "3. STOP. Reply with one line: 'Drafted tweet #<action_id>'."
        ),
    },
    "linkedin": {
        "label": "LinkedIn post",
        "max_iter": 4,
        "steps": (
            "1. (Optional) call `news_search` for a timely hook.\n"
            "2. Call `draft_linkedin_post` with the topic.\n"
            "3. STOP. Reply with: 'Drafted LinkedIn post #<action_id>'."
        ),
    },
    "hn_post": {
        "label": "Hacker News post",
        "max_iter": 4,
        "steps": (
            "1. Decide whether this is a `Show HN` (sharing) or `Ask HN` (asking).\n"
            "2. Call `draft_hn_post` with the topic and angle.\n"
            "3. STOP. Reply with: 'Drafted HN post #<action_id>'."
        ),
    },
    "article": {
        "label": "blog article",
        "max_iter": 6,
        "steps": (
            "1. Call `news_search` and/or `web_search` for 3-5 recent items on\n"
            "   the topic (with dates and sources).\n"
            "2. Call `draft_article` with target_keywords (derive 2-3 from the\n"
            "   topic) and pass the findings as `current_context`.\n"
            "3. STOP. Reply with: 'Drafted article #<action_id>'."
        ),
    },
    "reddit_reply": {
        "label": "Reddit reply",
        "max_iter": 6,
        "steps": (
            "1. Call `find_reddit_opportunities` with NO arguments. The 6-stage\n"
            "   pipeline returns items with suggested_angle, llm_reason (why),\n"
            "   and mention_product.\n"
            "2. Pick the highest-scoring item. Call `draft_reddit_reply` with:\n"
            "     post_url, post_title, post_body, subreddit,\n"
            "     product_angle  = item.suggested_angle\n"
            "     why_relevant   = item.llm_reason\n"
            "     mention_product = item.mention_product\n"
            "   The tool always produces 3 variants — works for both 'mention'\n"
            "   and 'no mention' cases. Do NOT use log_reddit_opportunity.\n"
            "3. STOP. Reply with: 'Drafted Reddit reply for r/<sub>'."
        ),
    },
    "reddit_opportunity": {
        # alias — same behavior as reddit_reply. The single Reddit action
        # type is `reddit_reply` (the UI surfaces why/angle for both).
        "label": "Reddit reply",
        "max_iter": 6,
        "steps": (
            "1. Call `find_reddit_opportunities` with NO arguments.\n"
            "2. For the top 1-2 items, call `draft_reddit_reply` passing\n"
            "   product_angle = item.suggested_angle,\n"
            "   why_relevant = item.llm_reason,\n"
            "   mention_product = item.mention_product.\n"
            "3. STOP."
        ),
    },
    "hn_opportunity": {
        "label": "Hacker News opportunity",
        "max_iter": 5,
        "steps": (
            "1. Call `find_hn_opportunities` with 3-5 product keywords.\n"
            "2. Pick the top 1-2 relevant threads and `log_hn_opportunity` each.\n"
            "3. STOP."
        ),
    },
    "seo_audit": {
        "label": "SEO audit",
        "max_iter": 8,
        "steps": (
            "1. Call `audit_seo` on the homepage URL.\n"
            "2. For each HIGH and MEDIUM finding, call `log_seo_fix` with the\n"
            "   severity, a concrete title, and clear fix instructions.\n"
            "3. STOP."
        ),
    },
    "competitor_scan": {
        "label": "competitor scan",
        "max_iter": 8,
        "steps": (
            "1. For the top 2 competitors, call `analyze_competitor` on each\n"
            "   competitor's URL (use `web_search` if a URL isn't known).\n"
            "2. Call `generate_competitor_analysis` to save the document.\n"
            "3. STOP."
        ),
    },
    "market_gap": {
        "label": "market gap",
        "max_iter": 8,
        "steps": (
            "1. Call `identify_market_gaps`. It will surface positioning gaps.\n"
            "2. STOP."
        ),
    },
    "strategy": {
        "label": "marketing strategy",
        "max_iter": 6,
        "steps": (
            "1. Call `generate_marketing_strategy(timeframe_days=30)`.\n"
            "2. STOP."
        ),
    },
}


async def run_targeted(
    *,
    config: Config,
    llm: LLM,
    store: ActionStore,
    project_id: int,
    run_id: int,
    target: str,
    topic: str = "",
    instruction: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """Generate ONE action of a specific kind. Fast, focused, single-purpose.

    Unlike `run_daily`, this doesn't span channels — it does one thing,
    saves the action, and stops. Designed for the "+" buttons in the UI.
    """
    project = store.get_project(project_id)
    if not project:
        raise ValueError(f"project {project_id} not found")

    playbook = _TARGET_PLAYBOOK.get(target)
    if not playbook:
        raise ValueError(f"unknown target '{target}'")

    registry = build_registry_for_run(config, llm, store, project_id, run_id)
    system = (
        f"You are Pulse — generating ONE {playbook['label']} for this project.\n"
        "Be ruthlessly focused. Execute the steps below exactly. Do not call\n"
        "tools that aren't listed. Do not generate multiple artifacts. STOP\n"
        "after the listed steps complete.\n\n"
        f"STEPS:\n{playbook['steps']}\n\n"
        "RULES:\n"
        " * Use tools, don't speculate.\n"
        " * If a step says 'Optional', skip it unless it clearly helps.\n"
        " * Do not call the same tool twice unless explicitly told to.\n\n"
        + _project_context(project)
    )

    topic_line = f"\nTOPIC / FOCUS: {topic}" if topic.strip() else ""
    extra = f"\nADDITIONAL INSTRUCTION: {instruction}" if instruction.strip() else ""
    user_content = (
        f"Generate one {playbook['label']} for {project['url']}.{topic_line}{extra}"
    )

    agent = Agent(
        llm=llm,
        registry=registry,
        system_prompt=system,
        max_iterations=min(playbook["max_iter"], config.agent.max_iterations),
    )
    async for ev in agent.stream([{"role": "user", "content": user_content}]):
        yield ev
