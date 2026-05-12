"""Run orchestrator — composes tools + system prompt for each run kind.

Three kinds of run:
  * first_dive — initial scan of a new project. Heavy on crawl + audit + voice.
  * daily      — recurring run. Generates a small set of ready-to-ship actions.
  * manual     — user-initiated ad-hoc run with a custom instruction.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import structlog

from .agent import Agent
from .config import Config
from .llm import LLM
from .store import ActionStore
from .tools import ToolRegistry
from .tools.crawl import make_crawl_tools
from .tools.discovery import make_discovery_tools
from .tools.documents import make_document_tools
from .tools.drafting import make_drafting_tools
from .tools.reddit import find_reddit_opportunities, make_reddit_tools
from .tools.seo import make_seo_tools
from .tools.strategy import make_strategy_tools
from .tools.web import make_web_tools

log = structlog.get_logger()


FIRST_DIVE_PROMPT = """\
You are Pulse — an AI marketing operator for indie founders. Today is the first
dive on a new project. The user has just signed up and given you their site URL.

GOAL: Build a complete picture of the product and produce a starter set of
marketing actions across every channel before you run out of iterations.

EXECUTE IN ORDER. Do NOT skip the drafting steps (5-7) — they're the user's
core value.

1. CRAWL with `crawl_website` (max_pages=10). Extract product, audience, pricing,
   tone.

2. CALL `update_project_info` with name, description, and competitors spotted
   on the site. Do this even if competitor info is sparse — you can always
   update later.

3. EXTRACT brand voice with `extract_brand_voice` using homepage hero + about +
   any blog excerpts as writing_samples.

4. CALL `generate_product_information` to save the Product Information document.

5. AUDIT SEO with `audit_seo` on the homepage. For high + medium findings, call
   `log_seo_fix`. Skip low unless fewer than 3 total.

6. DRAFT STARTER CONTENT (do not skip):
   - `draft_tweet`: introduce the product
   - `draft_article` (length=800): top-of-funnel topic relevant to the audience

7. GENERATE marketing strategy with `generate_marketing_strategy(timeframe_days=30)`.

8. FIND HN opportunities — ONE call to `find_hn_opportunities` with 3-5 product
   keywords. Then `log_hn_opportunity` on the 1-2 most relevant threads.

9. FIND REDDIT opportunities — ONE call to `find_reddit_opportunities` with
   3-5 product keywords (and subreddits if obvious — r/SideProject is common).
   Pick 1 thread that's an actual question your product answers and DRAFT a
   reply with `draft_reddit_reply` (paste post body in full). Log 1 other with
   `log_reddit_opportunity`. STOP after this. Do not search Reddit twice.

10. (Optional, if iterations remain) `web_search` for top 2 competitors, then
    `analyze_competitor` on each, then call `generate_competitor_analysis`
    to save the Competitor Analysis document, then `identify_market_gaps`.

STOP when done. Output a 3-5 line summary of what you generated.

RULES:
  * Use tools — don't speculate. Each call should be motivated by a result.
  * NEVER call the same tool more than once unless explicitly told to.
  * Reddit replies need 5+ sentences of real value before any product mention.
  * Drafts (steps 5-6) are non-negotiable. Skip step 9 before skipping 5-6.
"""


DAILY_PROMPT = """\
You are Pulse — an AI marketing operator for indie founders. This is the
user's recurring daily run. You already know the product (see project info
in the system context). Your job: produce 3-5 actions the user can ship
today in under 15 minutes total.

EXECUTE:

1. SEARCH HN with `find_hn_opportunities` for the product's keywords.
   For each genuinely relevant thread, log it with `log_hn_opportunity`.
   Cap at 2.

2. SEARCH Reddit with `find_reddit_opportunities`. If one of the threads
   is a clear question your product answers, DRAFT a reply with
   `draft_reddit_reply` (paste the post body in full). Otherwise log it
   with `log_reddit_opportunity` so the user can reply in their own voice.
   Cap at 2 Reddit actions.

3. CHOOSE one quick content piece and draft it:
   - a `draft_tweet` on a topical angle (look at recent news via
     `news_search` if needed to find one), OR
   - a `draft_linkedin_post`, OR
   - a `draft_hn_post` (rare — only if there's a launch-worthy update).
   Pick what fits today best. Don't draft all three.

4. RE-AUDIT SEO on the homepage with `audit_seo` — if there are new high
   or medium findings (compared to past runs), log them with `log_seo_fix`.
   Skip if no new issues.

STOP after 3-5 total actions. Output a single 2-3 line summary listing
what you generated and which to action first.

RULES:
  * Use tools, don't speculate.
  * Different angles than the last few daily runs — variety > repetition.
  * Cap total actions at 5. Quality > quantity.
  * Reddit replies must answer the actual question; copy-paste only.
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
    for t in make_crawl_tools():
        registry.add(t)
    for t in make_seo_tools(store=store, project_id=project_id):
        registry.add(t)
    for t in make_discovery_tools():
        registry.add(t)
    for t in make_drafting_tools(llm=llm, store=store, project_id=project_id, run_id=run_id):
        registry.add(t)
    for t in make_strategy_tools(llm=llm, store=store, project_id=project_id):
        registry.add(t)
    for t in make_document_tools(llm=llm, store=store, project_id=project_id):
        registry.add(t)
    registry.add(find_reddit_opportunities)
    for t in make_reddit_tools(llm=llm, store=store, project_id=project_id, run_id=run_id):
        if t.name == "find_reddit_opportunities":
            continue  # already added above as a free function
        registry.add(t)
    return registry


def _project_context(project: dict[str, Any]) -> str:
    bv = project.get("brand_voice")
    bv_block = ""
    if bv:
        bv_block = f"\nbrand voice tone: {bv.get('tone', '')}\nbrand voice taboo: {', '.join(bv.get('taboo') or [])}"
    return (
        f"PROJECT CONTEXT:\n"
        f"name: {project.get('name')}\n"
        f"url: {project.get('url')}\n"
        f"description: {project.get('description') or '(not yet inferred)'}\n"
        f"competitors: {', '.join(project.get('competitors') or []) or '(none known)'}"
        f"{bv_block}"
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


async def run_daily(
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
        system_prompt=DAILY_PROMPT + "\n\n" + _project_context(project),
        max_iterations=config.agent.max_iterations,
    )
    user_msg = {
        "role": "user",
        "content": f"Run today's daily pass for {project['url']}.",
    }
    async for ev in agent.stream([user_msg]):
        yield ev


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
