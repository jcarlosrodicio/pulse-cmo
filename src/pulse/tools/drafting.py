"""Content drafting tools.

These call back into the LLM with focused prompts to produce platform-shaped
content. They're separate from the orchestrator's reasoning model so we can
route drafts to a creativity-tuned model later. For MVP, same provider chain.

Each draft tool also persists an `action` row so the user sees it in their
feed immediately, with the draft body ready to copy-paste.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from ..llm import LLM, Message
from ..store import ActionStore
from ..text import strip_draft_preamble
from .registry import Tool, tool

log = structlog.get_logger()


HUMAN_TONE_RULES = """\
Write like a real human, not an AI assistant.
- never use em-dashes (—). use periods or commas.
- never say "I'd love to", "happy to help", "let me know if you have questions",
  "I hope this helps", "feel free to", "as an AI", "delve into", "in this digital age".
- vary sentence length. mix short punchy lines with longer thoughtful ones.
- casual punctuation is fine. lowercase first letters fine. occasional fragments fine.
- no bullet lists unless the content genuinely benefits.
- no closing call-to-action unless the user explicitly wants one.
- show, don't tell. specifics beat adjectives.\
"""

STRICT_OUTPUT_RULES = """\
OUTPUT FORMAT (non-negotiable):
- Output ONLY the final artifact. Nothing else.
- Do NOT narrate your process ("Let me think…", "The user wants…", "I'll draft…").
- Do NOT offer multiple options or variations.
- Do NOT explain what you wrote or why.
- Do NOT include preface, header, or sign-off text.
- The very first character of your response is the very first character
  of the artifact.\
"""


def _post_process_draft(text: str) -> str:
    """Apply the preamble strip and a final reasoning-tail cleanup."""
    from ..text import strip_draft_preamble, strip_reasoning
    return strip_draft_preamble(strip_reasoning(text)).strip().strip('"').strip("'")


VARIANT_MARKER = "---VARIANT---"

VARIANT_OUTPUT_RULES = (
    "OUTPUT FORMAT (non-negotiable):\n"
    "- Produce EXACTLY 3 distinct variants. Each variant should take a\n"
    "  meaningfully different angle (e.g. contrarian, story-led, data-led).\n"
    "- Separate variants with this exact line on its own, nothing else on\n"
    f"  that line:\n\n  {VARIANT_MARKER}\n\n"
    "- Do not number the variants. Do not label them. Do not add headings\n"
    "  like 'Variant 1' or 'Option A'. Start directly with the first variant.\n"
    "- Do NOT narrate your process. The first character of your response\n"
    "  is the first character of the first variant."
)


def _brand_voice_block(brand_voice: dict[str, Any] | None) -> str:
    if not brand_voice:
        return ""
    parts = []
    if brand_voice.get("tone"):
        parts.append(f"tone: {brand_voice['tone']}")
    if brand_voice.get("vocabulary"):
        parts.append(f"vocabulary signatures: {brand_voice['vocabulary']}")
    if brand_voice.get("taboo"):
        parts.append(f"never use: {', '.join(brand_voice['taboo'])}")
    if brand_voice.get("samples"):
        sample_text = "\n---\n".join(brand_voice["samples"][:3])
        parts.append(f"writing samples:\n{sample_text}")
    if not parts:
        return ""
    return "BRAND VOICE:\n" + "\n".join(parts)


async def _draft_with_llm(
    llm: LLM,
    *,
    system: str,
    user: str,
    temperature: float = 0.8,
    max_tokens: int = 2000,
) -> str:
    content = await llm.complete(
        [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return strip_draft_preamble(content.strip())


async def _draft_variants_with_llm(
    llm: LLM,
    *,
    system: str,
    user: str,
    n: int = 3,
    temperature: float = 0.85,
    max_tokens: int = 3000,
) -> list[str]:
    """Generate N draft variants in a single LLM call.

    Returns a list of cleaned-up variants. If parsing yields fewer than N,
    the helper pads the list with the same final variant rather than failing.
    """
    variants_system = (
        system
        + "\n\n"
        + VARIANT_OUTPUT_RULES.replace("EXACTLY 3", f"EXACTLY {n}")
    )
    raw = await llm.complete(
        [
            Message(role="system", content=variants_system),
            Message(role="user", content=user),
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    # The model is told to use the literal marker line; allow a bit of
    # whitespace slack around it.
    chunks = [c.strip() for c in raw.split(VARIANT_MARKER)]
    cleaned: list[str] = []
    for c in chunks:
        if not c:
            continue
        scrubbed = strip_draft_preamble(c).strip().strip('"').strip("'")
        if scrubbed:
            cleaned.append(scrubbed)
    if not cleaned:
        cleaned = [strip_draft_preamble(raw.strip())]
    # If the model emitted fewer than n, pad by repeating the last variant
    # so the UI never has to deal with a zero/jagged list.
    while len(cleaned) < n:
        cleaned.append(cleaned[-1])
    return cleaned[:n]


def make_drafting_tools(llm: LLM, store: ActionStore, project_id: int, run_id: int) -> list[Tool]:
    """Bind drafting tools to a specific (project, run) so each draft auto-saves."""

    async def _save_action(action_type: str, title: str, content: str, context: dict[str, Any]) -> int:
        return store.create_action(
            project_id=project_id,
            run_id=run_id,
            action_type=action_type,
            title=title,
            content=content,
            context=context,
        )

    @tool
    async def draft_tweet(topic: str, angle: str = "") -> str:
        """Draft a single tweet (or short thread up to 3 tweets) on a topic.

        Saves the draft as an action. Return value is the draft text and the
        action id so the orchestrator can reference it.

        Args:
            topic: What the tweet should be about.
            angle: Optional angle/take (e.g., "contrarian", "behind the scenes").
        """
        bv = store.get_brand_voice(project_id)
        bv_block = _brand_voice_block(bv)
        system = (
            "You draft tweets for an indie founder. Output ONLY the tweet text, "
            "no quotes, no preface, no explanation. If a thread is warranted, "
            "use blank lines to separate tweets, max 3 tweets, each under 280 chars. "
            "Default to a single tweet.\n\n"
            + HUMAN_TONE_RULES
            + "\n\n" + STRICT_OUTPUT_RULES
            + ("\n\n" + bv_block if bv_block else "")
        )
        user = f"topic: {topic}\nangle: {angle or '(your call)'}"
        variants = await _draft_variants_with_llm(
            llm, system=system, user=user, n=3, temperature=0.9, max_tokens=1800
        )
        action_id = await _save_action(
            "tweet",
            title=topic[:80],
            content=variants[0],
            context={
                "angle": angle,
                "variants": variants,
                "chosen_variant": 0,
            },
        )
        return json.dumps(
            {"ok": True, "action_id": action_id, "draft": variants[0], "variants": len(variants)}
        )

    @tool
    async def draft_hn_post(topic: str, angle: str) -> str:
        """Draft a Show HN or Ask HN post.

        Args:
            topic: What you're sharing or asking.
            angle: 'show' (Show HN — sharing a project), 'ask' (Ask HN — asking the
                community), or a specific framing string.
        """
        bv = store.get_brand_voice(project_id)
        kind_hint = "Show HN" if angle.lower().startswith("show") else (
            "Ask HN" if angle.lower().startswith("ask") else "HN post"
        )
        system = (
            f"Draft a {kind_hint} post. HN audience hates marketing fluff. "
            "Lead with the technical or concrete substance. Title: under 80 chars, "
            "no clickbait. Body: 2-4 short paragraphs. Output as:\n"
            "TITLE: <title>\n\n<body>\n\n"
            + HUMAN_TONE_RULES
            + "\n\n" + STRICT_OUTPUT_RULES
            + ("\n\n" + _brand_voice_block(bv) if bv else "")
        )
        user = f"topic: {topic}\nangle: {angle}"
        variants = await _draft_variants_with_llm(
            llm, system=system, user=user, n=3, temperature=0.8, max_tokens=2400
        )
        action_id = await _save_action(
            "hn_post",
            title=topic[:80],
            content=variants[0],
            context={
                "angle": angle,
                "variants": variants,
                "chosen_variant": 0,
            },
        )
        return json.dumps(
            {"ok": True, "action_id": action_id, "draft": variants[0], "variants": len(variants)}
        )

    @tool
    async def draft_linkedin_post(topic: str, angle: str = "") -> str:
        """Draft a LinkedIn post — slightly more formal than tweet, no hashtag spam.

        Args:
            topic: Subject of the post.
            angle: Optional framing.
        """
        bv = store.get_brand_voice(project_id)
        system = (
            "Draft a LinkedIn post (150-300 words). Professional but not corporate. "
            "Lead with a hook that's specific, not generic. No hashtag spam (max 2). "
            "No 'agree?' or 'thoughts?' at the end.\n\n"
            + HUMAN_TONE_RULES
            + "\n\n" + STRICT_OUTPUT_RULES
            + ("\n\n" + _brand_voice_block(bv) if bv else "")
        )
        user = f"topic: {topic}\nangle: {angle or '(your call)'}"
        variants = await _draft_variants_with_llm(
            llm, system=system, user=user, n=3, temperature=0.8, max_tokens=2800
        )
        action_id = await _save_action(
            "linkedin",
            title=topic[:80],
            content=variants[0],
            context={
                "angle": angle,
                "variants": variants,
                "chosen_variant": 0,
            },
        )
        return json.dumps(
            {"ok": True, "action_id": action_id, "draft": variants[0], "variants": len(variants)}
        )

    @tool
    async def draft_article(topic: str, target_keywords: list[str], length: int = 800) -> str:
        """Draft a blog article in markdown, optimized for the target keywords.

        Args:
            topic: Article topic.
            target_keywords: 1-5 SEO keywords to weave in naturally.
            length: Target word count (default 800).
        """
        length = max(300, min(int(length), 2500))
        bv = store.get_brand_voice(project_id)
        kw = ", ".join(target_keywords[:5])
        system = (
            "Draft a blog article in clean markdown. Use a clear H1, then 3-6 H2 sections. "
            "Hit the target word count within ±20%. Weave the keywords in naturally — "
            "do not stuff. Concrete examples > generic advice.\n\n"
            + HUMAN_TONE_RULES
            + "\n\n" + STRICT_OUTPUT_RULES
            + ("\n\n" + _brand_voice_block(bv) if bv else "")
        )
        user = f"topic: {topic}\ntarget keywords: {kw}\ntarget length: ~{length} words"
        body = await _draft_with_llm(llm, system=system, user=user, temperature=0.7)
        action_id = await _save_action(
            "article",
            title=topic[:120],
            content=body,
            context={"target_keywords": target_keywords, "target_length": length},
        )
        return json.dumps(
            {"ok": True, "action_id": action_id, "draft_preview": body[:600] + "…" if len(body) > 600 else body, "length_chars": len(body)}
        )

    @tool
    async def log_seo_fix(severity: str, title: str, description: str, fix_instructions: str) -> str:
        """Record an SEO fix as an actionable item for the user.

        Use this to convert audit_seo findings into items in the action feed.
        Severity should be 'high', 'medium', or 'low'.

        Args:
            severity: high | medium | low.
            title: Short title (e.g., 'Add meta description to homepage').
            description: One-line description of what's wrong.
            fix_instructions: Concrete steps to fix it.
        """
        sev = severity.lower()
        if sev not in ("high", "medium", "low"):
            sev = "medium"
        action_id = await _save_action(
            "seo_fix",
            title=title[:120],
            content=fix_instructions,
            context={"severity": sev, "description": description},
        )
        return json.dumps({"ok": True, "action_id": action_id, "severity": sev})

    @tool
    async def log_hn_opportunity(hn_url: str, title: str, why_relevant: str, suggested_angle: str) -> str:
        """Record an HN opportunity as an action.

        Use after find_hn_opportunities surfaces something worth engaging with.
        The user goes to hn_url and comments themselves (no auto-post).

        Args:
            hn_url: Direct HN thread URL.
            title: HN post title.
            why_relevant: One sentence on why this matches the product.
            suggested_angle: How the user should approach the comment (not a draft).
        """
        action_id = await _save_action(
            "hn_opportunity",
            title=title[:120],
            content=f"**Why relevant:** {why_relevant}\n\n**Suggested angle:** {suggested_angle}\n\n**Link:** {hn_url}",
            context={"hn_url": hn_url, "why": why_relevant, "angle": suggested_angle},
        )
        return json.dumps({"ok": True, "action_id": action_id})

    return [
        draft_tweet,
        draft_hn_post,
        draft_linkedin_post,
        draft_article,
        log_seo_fix,
        log_hn_opportunity,
    ]
