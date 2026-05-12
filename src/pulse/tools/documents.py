"""Document generators — structured markdown briefs the user can read.

Each generator:
  * pulls relevant context from the project (description, competitors, crawl)
  * asks the LLM for a structured markdown brief
  * upserts the result in the `documents` table

Kinds:
  * product_information  — overview, what it does, audience, business model
  * competitor_analysis  — per-competitor positioning + comparison matrix
  * brand_voice          — extracted voice profile expanded into a usable doc
  * marketing_strategy   — already exists as an action, mirrored into documents

Bound to (store, project_id) via a factory like other run-scoped tools.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from ..llm import LLM, Message
from ..store import ActionStore
from ..text import strip_reasoning
from .registry import Tool, tool

log = structlog.get_logger()


PRODUCT_INFO_SYSTEM = """\
You produce a polished one-pager brief on an indie product.

Output STRICT markdown in this exact structure (use the same heading text):

## Overview

**Product Name:** <name>

**Website:** <url>

**One-liner:** <single sentence elevator pitch>

## What It Does

<one or two short paragraphs explaining the product's actual function — write
specifically, not generically>

## Product Category

- <category 1>
- <category 2>
- <category 3>

## Target Customers

<one paragraph describing who uses this and why>

## Business Model

<short paragraph: pricing model, revenue mechanism, free tier (if any)>

OUTPUT RULES (non-negotiable):
- Output ONLY the markdown above. No preface, no narration, no "Let me think…".
- Never invent pricing tiers or features you don't have evidence for.
- If a section can't be answered from the provided context, write "Unknown — needs research."
"""


COMPETITOR_ANALYSIS_SYSTEM = """\
You produce a competitive analysis brief for an indie product.

Output STRICT markdown in this exact structure (use the same heading text):

## Overview

<one short paragraph summarizing the competitive landscape>

## Direct Competitors

For each direct competitor (max 5), use this sub-structure:

### <Competitor Name>

- **Website:** <url if known, otherwise omit>
- **Positioning:** <one sentence on how they pitch themselves>
- **Strengths:** <one sentence>
- **Weaknesses:** <one sentence — be honest>
- **What we do differently:** <one sentence on the user's edge vs them>

## Where We Win

<paragraph: angles where the user's product has the strongest case>

## Where We're Behind

<paragraph: be honest about gaps the user should know>

OUTPUT RULES:
- Output ONLY the markdown above. No preface.
- Use concrete details where possible.
- If competitor info is sparse, say so in their bullets ("limited public info").
"""


BRAND_VOICE_SYSTEM = """\
You produce a brand voice document for the user's drafting tools.

Output STRICT markdown in this exact structure:

## Tone

<2-4 words capturing the tone>

## Vocabulary

<paragraph: signature words, phrases, and lexical choices>

## Sentence Rhythm

<paragraph: short vs long, fragments, punctuation habits>

## Taboo

- <word/phrase to avoid>
- <word/phrase to avoid>
- <word/phrase to avoid>

## Sample Voice

> <one short example sentence in this voice>

OUTPUT RULES:
- Output ONLY the markdown above. No preface, no narration.
"""


async def _produce_document(
    llm: LLM,
    *,
    system: str,
    user: str,
    max_tokens: int = 1800,
    temperature: float = 0.45,
) -> str:
    raw = await llm.complete(
        [Message(role="system", content=system), Message(role="user", content=user)],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return strip_reasoning(raw).strip()


async def _build_product_information_user(project: dict[str, Any]) -> str:
    parts = [
        f"Product name: {project.get('name')}",
        f"Website: {project.get('url')}",
        f"Description (may be empty): {project.get('description') or '(none yet)'}",
    ]
    competitors = project.get("competitors") or []
    if competitors:
        parts.append("Known competitors: " + ", ".join(competitors))
    bv = project.get("brand_voice") or {}
    if bv.get("tone"):
        parts.append(f"Brand voice tone: {bv['tone']}")
    return "\n".join(parts)


async def _build_competitor_analysis_user(project: dict[str, Any]) -> str:
    parts = [
        f"Product: {project.get('name')} ({project.get('url')})",
        f"About: {project.get('description') or '(unknown)'}",
    ]
    competitors = project.get("competitors") or []
    if competitors:
        parts.append("Competitors to analyze: " + ", ".join(competitors))
    else:
        parts.append("Competitors: none specified yet — note this in the brief.")
    return "\n".join(parts)


async def regenerate_document_for_project(
    *,
    llm: LLM,
    store: ActionStore,
    project_id: int,
    kind: str,
) -> int:
    project = store.get_project(project_id)
    if not project:
        raise ValueError(f"project {project_id} not found")

    if kind == "product_information":
        body = await _produce_document(
            llm,
            system=PRODUCT_INFO_SYSTEM,
            user=await _build_product_information_user(project),
        )
        title = "Product Information"
    elif kind == "competitor_analysis":
        body = await _produce_document(
            llm,
            system=COMPETITOR_ANALYSIS_SYSTEM,
            user=await _build_competitor_analysis_user(project),
            max_tokens=2400,
        )
        title = "Competitor Analysis"
    elif kind == "brand_voice":
        bv = project.get("brand_voice") or {}
        if not bv.get("tone") and not bv.get("samples"):
            body = (
                "## Tone\n\nUnknown — needs research.\n\n"
                "## Vocabulary\n\nUnknown — needs research.\n\n"
                "## Sentence Rhythm\n\nUnknown — needs research.\n\n"
                "## Taboo\n\n- em-dashes\n- AI tells\n\n"
                "## Sample Voice\n\n> (no sample yet)\n"
            )
        else:
            user_input = (
                f"Tone: {bv.get('tone', '')}\n"
                f"Vocabulary: {bv.get('vocabulary', '')}\n"
                f"Rhythm: {bv.get('rhythm', '')}\n"
                f"Taboo: {', '.join(bv.get('taboo') or [])}\n"
                f"Sample 1: {(bv.get('samples') or [''])[0][:400]}\n"
            )
            body = await _produce_document(
                llm, system=BRAND_VOICE_SYSTEM, user=user_input
            )
        title = "Brand Voice"
    elif kind == "marketing_strategy":
        # Pull from the latest 'strategy' action if present.
        actions = store.list_actions(project_id)
        strat = next((a for a in actions if a["action_type"] == "strategy"), None)
        if strat:
            body = strat["content"]
            title = strat["title"] or "Marketing Strategy"
        else:
            body = "_No strategy yet. Run a daily pass to generate one._"
            title = "Marketing Strategy"
    else:
        raise ValueError(f"unknown document kind: {kind}")

    doc_id = store.upsert_document(
        project_id=project_id, kind=kind, title=title, content_md=body
    )
    return doc_id


def make_document_tools(
    llm: LLM, store: ActionStore, project_id: int
) -> list[Tool]:
    """Tools the agent calls to write structured documents during a first dive."""

    @tool
    async def generate_product_information() -> str:
        """Generate the project's Product Information document.

        Call this AFTER crawl_website + update_project_info on the first dive,
        so the document reflects the inferred description and competitor list.
        Saves to the documents table; replaces any existing version.
        """
        doc_id = await regenerate_document_for_project(
            llm=llm,
            store=store,
            project_id=project_id,
            kind="product_information",
        )
        return json.dumps({"ok": True, "document_id": doc_id})

    @tool
    async def generate_competitor_analysis() -> str:
        """Generate the Competitor Analysis document.

        Call this AFTER analyze_competitor has been run on 2-3 competitors and
        their positioning notes are in your context. Saves to documents.
        """
        doc_id = await regenerate_document_for_project(
            llm=llm,
            store=store,
            project_id=project_id,
            kind="competitor_analysis",
        )
        return json.dumps({"ok": True, "document_id": doc_id})

    return [generate_product_information, generate_competitor_analysis]
