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
from .tools.reddit import make_reddit_tools
from .tools.seo import make_seo_tools
from .tools.geo import make_geo_tools
from .tools.strategy import make_strategy_tools
from .tools.web import make_web_tools

log = structlog.get_logger()


FIRST_DIVE_PROMPT = """\
You are Pulse — an AI marketing operator for indie founders. Today is the first
dive on a new project. The user has just signed up and given you their site URL.

GOAL: Diagnose the product properly, then produce a tight set of marketing
actions grounded in that diagnosis. A considered strategy beats a pile of
generic posts. If a MARKETING BRIEF is in the context below, every output must
serve the founder's stated goal, ICP, and constraints.

EXECUTE IN ORDER. The diagnosis (steps 6-8) is the priority — it makes
everything else specific instead of generic.

1. CRAWL with `crawl_website` (max_pages=10). Extract product, audience, pricing,
   tone. If the URL is a GitHub repo, crawl_website returns clean repo metadata
   (stars, language, license, topics) + the README — use that as the product
   picture, and if the repo has a `homepage`, treat THAT as the site for the
   SEO/GEO/links audits.

2. CALL `update_project_info` with name, description, and competitors spotted
   on the site (even if sparse).

3. EXTRACT brand voice with `extract_brand_voice` using homepage hero + about +
   any blog excerpts as writing_samples.

4. CALL `generate_product_information` to save the Product Information document.

5. AUDIT SEO with `audit_seo` on the homepage (for a GitHub project, use the
   repo's `homepage` URL if it has one; skip if a repo with no homepage). For
   high + medium findings, call `log_seo_fix`. Skip low unless fewer than 3
   total. Then call `audit_geo` and `audit_links` on the same URL — one call
   each. Log any HIGH GEO finding with `log_seo_fix`.

6. RESEARCH COMPETITORS (do this BEFORE the brain so it's grounded): for the top
   1-2 competitors, `analyze_competitor` on each competitor URL (use
   `web_search` if you don't know the URL). Their reads are saved automatically.
   Cap at 2.

7. BUILD THE PRODUCT BRAIN: call `build_product_brain` (no arguments). It
   distills everything so far — crawl, brief, competitor reads — into the SHARED
   intelligence: the WEDGE, the ICP and their exact vocabulary, the communities
   they live in, and intent-grouped search queries. Every step below conditions
   on it, so output is specific to THIS product, not generic. Do this before
   positioning.

8. DIAGNOSE: call `generate_positioning_doc` (no arguments) — situation read,
   ICP, value prop, the WEDGE, ranked channels, north-star metric. The spine.

9. GENERATE the plan: `generate_marketing_strategy(timeframe_days=30)`. Builds
   on the positioning + brain — a sequenced plan with a leading indicator on
   every item, not a generic checklist.

10. DRAFT STARTER CONTENT, on-wedge (do not skip):
    - `draft_tweet`: introduce the product, aligned to the wedge. one tweet.
    - BEFORE the article: call `news_search`/`web_search` for the category to
      find 3-5 recent items (dates + sources), then `draft_article` (length=800)
      passing them as `current_context`.

11. FIND HN opportunities — ONE call to `find_hn_opportunities` with 3-5
    keywords drawn from the brain (use its category terms + competitor names,
    not just the product name). `log_hn_opportunity` on the 1-2 most relevant.

12. FIND REDDIT opportunities — ONE call to `find_reddit_opportunities` with NO
    arguments. Items include `suggested_angle`, `mention_product`, `llm_reason`,
    `final_score`. Pick the TOP 1-2. For each, `draft_reddit_reply` with:
      - post_url, post_title, post_body (paste in full), subreddit
      - product_angle  = item's `suggested_angle`
      - why_relevant   = item's `llm_reason`
      - mention_product = item's `mention_product`
    Do NOT call `log_reddit_opportunity`. Never search Reddit twice.

13. SAVE the Competitor Analysis document with `generate_competitor_analysis`,
    then `identify_market_gaps` (both read the competitor reads from step 6).

STOP when done. Output a 3-5 line summary of what you generated.

RULES:
  * Use tools — don't speculate. Each call should be motivated by a result.
  * NEVER call the same tool more than once unless explicitly told to.
  * Anchor EVERY output on the product brain's wedge + ICP vocabulary. If a
    suggestion would apply to any product, it's wrong — make it specific.
  * Reddit replies need 5+ sentences of real value before any product mention.
  * Steps 7-12 (brain, positioning, strategy, a content draft, HN, AND Reddit)
    are the core deliverables — make sure they ALL complete. Step 13 (competitor
    doc + gaps) is the only one to drop if you run low on iterations.
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

2. SEARCH Reddit with `find_reddit_opportunities` (call with NO arguments).
   For the top 1-2 items, call `draft_reddit_reply` passing:
     - post_url, post_title, post_body, subreddit (from the item)
     - product_angle  = item's `suggested_angle`
     - why_relevant   = item's `llm_reason`
     - mention_product = item's `mention_product` (true/false)
   The tool always produces 3 reply variants — handle both
   "mention product" and "no mention" cases. Do not use
   `log_reddit_opportunity`. Cap at 2 Reddit actions.

3. CHOOSE one quick content piece. ALWAYS check `news_search` first for a
   timely angle in the product's category (today + last 48h). Then draft:
   - `draft_tweet` on the news hook, OR
   - `draft_linkedin_post`, OR
   - `draft_article` (if there's a clear, fresh story worth a 600-900 word
     piece, pass the news findings as `current_context`), OR
   - `draft_hn_post` (rare — only if there's a launch-worthy update).
   Pick what fits today best. Don't draft all of them.

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
    for t in make_geo_tools(store=store, project_id=project_id):
        registry.add(t)
    for t in make_discovery_tools(store, project_id, llm):
        registry.add(t)
    for t in make_drafting_tools(llm=llm, store=store, project_id=project_id, run_id=run_id):
        registry.add(t)
    for t in make_strategy_tools(llm=llm, store=store, project_id=project_id):
        registry.add(t)
    for t in make_document_tools(llm=llm, store=store, project_id=project_id):
        registry.add(t)
    for t in make_reddit_tools(llm=llm, store=store, project_id=project_id, run_id=run_id):
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
