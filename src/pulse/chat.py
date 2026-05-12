"""Chat agent — multi-session conversations about a project.

Each session has its own message history. The agent has the same toolset
as orchestrator runs (so the user can ask "draft a tweet on X" inline),
but no first_dive/daily prompt — just a free-form CMO assistant prompt.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import structlog

from .agent import Agent
from .config import Config
from .llm import LLM
from .orchestrator import _project_context, build_registry_for_run
from .store import ActionStore
from .tools.documents import regenerate_document_for_project  # re-export for server

__all__ = ["stream_chat_reply", "expand_action_detail", "regenerate_document_for_project"]
_ = regenerate_document_for_project  # silence unused-import linter

log = structlog.get_logger()

CHAT_PROMPT = """\
You are Pulse — the indie founder's AI CMO. You're embedded in their dashboard
and have full context on their product (see PROJECT below). They might ask:

  * "draft a tweet on X" — use draft_tweet
  * "what should I post on LinkedIn this week?" — use draft_linkedin_post
  * "check if my homepage SEO is still good" — use audit_seo
  * "any new HN threads I should reply to?" — use find_hn_opportunities
  * strategic questions (positioning, pricing, content angles)
  * tactical asks ("rewrite this draft to be punchier")

Be tight and concrete. Match their energy. No marketing fluff in your replies.
When you create an action via a draft_* tool, mention the action briefly so
they know it landed in their feed.
"""


async def stream_chat_reply(
    *,
    config: Config,
    llm: LLM,
    store: ActionStore,
    project_id: int,
    session_id: int,
    user_message: str,
) -> AsyncIterator[dict[str, Any]]:
    project = store.get_project(project_id)
    if not project:
        raise ValueError(f"project {project_id} not found")

    # persist the user message immediately
    store.add_chat_message(session_id, "user", user_message)

    # rebuild history
    history_rows = store.list_chat_messages(session_id)
    messages = [
        {"role": r["role"], "content": r["content"]} for r in history_rows
    ]

    # tools — share the same registry as runs so chat can draft / audit / search
    latest_run_id = store.latest_run_id(project_id) or 0
    registry = build_registry_for_run(config, llm, store, project_id, latest_run_id)

    agent = Agent(
        llm=llm,
        registry=registry,
        system_prompt=CHAT_PROMPT + "\n\n" + _project_context(project),
        max_iterations=8,
    )

    assistant_buf: list[str] = []
    async for ev in agent.stream(messages):
        if ev.get("type") == "text":
            assistant_buf.append(ev["text"])
        elif ev.get("type") == "done":
            full = ev.get("content") or "".join(assistant_buf)
            store.add_chat_message(session_id, "assistant", full)
            # auto-title brand-new sessions on the first reply
            sess = store.get_chat_session(session_id)
            if sess and sess["title"] == "New conversation":
                title = user_message.strip().splitlines()[0][:60]
                if title:
                    store.rename_chat_session(session_id, title)
        yield ev


async def expand_action_detail(
    *,
    llm: LLM,
    store: ActionStore,
    action_id: int,
) -> str:
    """Generate a richer step-by-step remediation guide for an action.

    Cached on the action row after generation.
    """
    action = store.get_action(action_id)
    if not action:
        raise ValueError(f"action {action_id} not found")

    if action.get("detail_md"):
        return action["detail_md"]

    project = store.get_project(action["project_id"])
    if not project:
        raise ValueError("project not found")

    from .llm import Message

    system = (
        "You write detailed, actionable remediation guides for SEO findings, "
        "content drafts, and marketing opportunities. Output clean markdown. "
        "Structure:\n\n"
        "## Overview\n"
        "<2-3 sentences explaining the issue and its impact>\n\n"
        "## Steps\n"
        "1. <step with explicit details, code, examples>\n"
        "2. <step>\n"
        "3. <validation step>\n"
        "4. <where to apply the change in their stack — be specific>\n\n"
        "## Why this matters\n"
        "<one paragraph: business outcome, search ranking impact, conversion impact>\n\n"
        "Use fenced code blocks for code/HTML/configs. Be concrete — name file paths, "
        "tag names, exact strings. No generic SEO platitudes."
    )

    ctx_str = ""
    if action["context"]:
        ctx_str = f"\nContext: {action['context']}"

    user = (
        f"Product: {project['name']} ({project['url']})\n"
        f"Description: {project.get('description') or '(unknown)'}\n\n"
        f"Action type: {action['action_type']}\n"
        f"Title: {action['title']}\n"
        f"Content / fix instructions: {action['content']}"
        f"{ctx_str}\n\n"
        "Write the remediation guide."
    )

    detail = await llm.complete(
        [Message(role="system", content=system), Message(role="user", content=user)],
        temperature=0.4,
        max_tokens=1800,
    )
    detail = detail.strip()
    store.set_action_detail(action_id, detail)
    return detail
