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
Write like a real founder, not an AI assistant. Small character energy.

HARD BANS (do not violate):
- no em-dashes (—). ever. use periods, commas, or a new sentence.
- no emojis. ever. not even one. not in titles, not at the end.
- no hashtags (except LinkedIn, max 1, only if it's not a vibes word).
- no marketing words: leverage, robust, synergy, seamless, comprehensive,
  unlock, empower, supercharge, game-changer, revolutionize, cutting-edge,
  innovative solution, in this digital age, in today's world.
- no AI-assistant phrases: "I'd love to", "happy to help", "let me know if",
  "I hope this helps", "feel free to", "as an AI", "delve into", "navigate",
  "tapestry", "in the realm of", "it's important to note".
- no closing call-to-action ("check it out", "let me know what you think",
  "drop a comment") unless the user explicitly requested one.

VOICE (positive direction):
- founder-to-founder. like you're texting a friend who also runs a thing.
- short. cut every word that isn't earning its keep. one idea per sentence is fine.
- lowercase first letters are fine. fragments are fine. one-word lines are fine.
- specific numbers beat adjectives. "$800/mo" beats "expensive". "11pm friday"
  beats "late at night". "3 customers" beats "some customers".
- contractions everywhere. "we're", "i'm", "don't", "won't". no "we are" robotics.
- vary sentence length. punchy. then a longer thought that actually goes somewhere.
  then punchy again. that's the rhythm.
- show the seams. real founders admit when something sucked or surprised them.
  "this took 4 tries" lands harder than "we iterated rapidly".
- if a sentence could be in a McKinsey deck, kill it.\
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
    from .reddit import _scrub
    return _scrub(strip_draft_preamble(strip_reasoning(text)).strip().strip('"').strip("'"))


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
    from .reddit import _scrub
    content = await llm.complete(
        [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _scrub(strip_draft_preamble(content.strip()))


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
    from .reddit import _scrub
    chunks = [c.strip() for c in raw.split(VARIANT_MARKER)]
    cleaned: list[str] = []
    for c in chunks:
        if not c:
            continue
        scrubbed = _scrub(strip_draft_preamble(c).strip().strip('"').strip("'"))
        if scrubbed:
            cleaned.append(scrubbed)
    if not cleaned:
        cleaned = [_scrub(strip_draft_preamble(raw.strip()))]
    # If the model emitted fewer than n, pad by repeating the last variant
    # so the UI never has to deal with a zero/jagged list.
    while len(cleaned) < n:
        cleaned.append(cleaned[-1])
    return cleaned[:n]


GROUND_RULE = (
    "GROUND IT: lead with the product's WEDGE, write in the ICP's exact "
    "vocabulary, and reference real features / competitors from the brain above. "
    "Never write a line that could be about any other product — make it specific "
    "to THIS one."
)


def make_drafting_tools(llm: LLM, store: ActionStore, project_id: int, run_id: int) -> list[Tool]:
    """Bind drafting tools to a specific (project, run) so each draft auto-saves."""

    def _ground() -> str:
        """The Product Brain + a grounding rule, appended to every draft prompt so
        content is specific to this product (the wedge + the ICP's own words),
        not generic. Empty until the Brain exists."""
        from ..product_brain import brain_context_block

        bb = brain_context_block(store.get_product_brain(project_id))
        return ("\n\n" + bb + "\n\n" + GROUND_RULE) if bb else ""

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
            "You draft tweets/X posts for an indie founder who tweets like a real\n"
            "CEO who actually ships, not a content marketer.\n\n"
            "TWEET SHAPE:\n"
            "- default to ONE tweet. only thread if the idea genuinely can't fit.\n"
            "- max 3 tweets in a thread. each under 280 chars (count it).\n"
            "- the first line is the whole game. it's a hook OR it's nothing.\n"
            "- think 'mid-conversation text to a friend', not 'announcement'.\n"
            "- the best tweets feel slightly unfinished. resist polishing the edges.\n\n"
            "DO:\n"
            "- contractions. lowercase first letters. fragments.\n"
            "- specific numbers, dates, dollar amounts. concrete details.\n"
            "- the actual surprising bit you noticed. the contrarian beat.\n"
            "- end on a thought, not a CTA.\n\n"
            "DON'T:\n"
            "- emojis. hashtags. quotation marks around the whole thing.\n"
            "- 'i just shipped', 'excited to announce', 'here's a thread on'.\n"
            "- threads with '1/', '2/'. blank line between tweets is enough.\n"
            "- rhetorical questions ('ever notice that...?').\n"
            "- the word 'literally' unless something literally is the case.\n\n"
            + HUMAN_TONE_RULES
            + "\n\n" + STRICT_OUTPUT_RULES
            + ("\n\n" + bv_block if bv_block else "")
            + _ground()
        )
        user = f"topic: {topic}\nangle: {angle or '(your call. pick the most specific/surprising read.)'}"
        variants = await _draft_variants_with_llm(
            llm, system=system, user=user, n=3, temperature=0.95, max_tokens=1800
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
            f"Draft a {kind_hint} post. HN readers are smart engineers who will\n"
            "rip apart anything that smells like marketing. They reward specificity\n"
            "and technical honesty. They downvote vibes.\n\n"
            "TITLE:\n"
            "- under 80 chars. no clickbait. no colons-then-clever-tagline.\n"
            "- 'Show HN: <one-line of what it is>'. plain. specific. boring is fine.\n"
            "- if a number or stack mention sharpens it, include it.\n"
            "- never use exclamation marks.\n\n"
            "BODY (2-4 short paragraphs):\n"
            "- first paragraph: what it does, in plain words, in one or two sentences.\n"
            "  the stack and the boring details. no 'tired of X? we built Y'.\n"
            "- next: WHY you built it. the actual itch. honest, not a pitch.\n"
            "  what surprised you. what's still rough.\n"
            "- end with what feedback would help, or a concrete open question.\n"
            "  no 'would love to hear your thoughts'. just ask the real thing.\n\n"
            "OUTPUT FORMAT:\n"
            "TITLE: <title>\n\n<body>\n\n"
            + HUMAN_TONE_RULES
            + "\n\n" + STRICT_OUTPUT_RULES
            + ("\n\n" + _brand_voice_block(bv) if bv else "")
            + _ground()
        )
        user = f"topic: {topic}\nangle: {angle}"
        variants = await _draft_variants_with_llm(
            llm, system=system, user=user, n=3, temperature=0.85, max_tokens=2400
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
            "Draft a LinkedIn post. Founder voice, not consultant voice. People\n"
            "are scrolling through 40 of these. Earn the first 3 seconds.\n\n"
            "SHAPE:\n"
            "- 120-280 words. shorter is almost always better.\n"
            "- first line is a hook that promises a specific payoff. one line.\n"
            "  blank line after. that's the scroll-stopper.\n"
            "- short paragraphs. 1-3 lines each. lots of white space.\n"
            "- end with a concrete observation or a small lesson. not a question.\n"
            "  never end with 'agree?', 'thoughts?', 'what would you add?'.\n\n"
            "DO:\n"
            "- tell one story or one specific data point. not three.\n"
            "- name the company / number / date / dollar amount. concrete.\n"
            "- be honest about what went wrong. linkedin rewards that more than wins.\n"
            "- one hashtag max, only if it's a category tag (#startups), never a vibes tag.\n\n"
            "DON'T:\n"
            "- 'I want to share something important...'\n"
            "- 'Here's a lesson I learned this week:'\n"
            "- 'PSA:' / 'Reminder:' openers.\n"
            "- the broetry one-line-per-sentence-for-no-reason format.\n"
            "- enumerated lists ('5 things I learned...'). cliché.\n"
            "- emojis. bullet glyphs. arrows. line dividers like '—————'.\n\n"
            + HUMAN_TONE_RULES
            + "\n\n" + STRICT_OUTPUT_RULES
            + ("\n\n" + _brand_voice_block(bv) if bv else "")
            + _ground()
        )
        user = f"topic: {topic}\nangle: {angle or '(your call. pick the angle that lets you be most specific.)'}"
        variants = await _draft_variants_with_llm(
            llm, system=system, user=user, n=3, temperature=0.85, max_tokens=2800
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
    async def draft_article(
        topic: str,
        target_keywords: list[str],
        length: int = 800,
        current_context: str = "",
    ) -> str:
        """Draft a blog article in markdown, optimized for the target keywords.

        IMPORTANT: before calling this, run `web_search` and/or `news_search`
        for the topic + key entity names and paste the most useful 3-6 findings
        (with dates and source names) into `current_context`. The article will
        reference them inline so it feels current and reported, not generic.

        Args:
            topic: Article topic.
            target_keywords: 1-5 SEO keywords to weave in naturally.
            length: Target word count (default 800).
            current_context: Optional. Recent news/quotes/numbers (with source
                + date) that should be referenced inline. Format freely.
        """
        length = max(300, min(int(length), 2500))
        bv = store.get_brand_voice(project_id)
        kw = ", ".join(target_keywords[:5])
        has_context = bool(current_context.strip())
        system = (
            "You're ghostwriting a blog post for an indie founder. The voice is\n"
            "candid, a little dry, occasionally funny. Think 'a smart friend who\n"
            "just figured something out and is telling you about it over coffee',\n"
            "not 'SEO content marketer'. Substance over polish.\n\n"
            "STRUCTURE (markdown):\n"
            "- one H1 at the top. specific. no colon-then-clever-tagline trick.\n"
            "- open with a real moment, observation, or stat. not 'in today's\n"
            "  fast-paced world'. not 'imagine if'. drop the reader into something.\n"
            "- 3-6 H2 sections. each H2 is a real claim or beat, not a generic\n"
            "  signpost like 'introduction' or 'conclusion'.\n"
            "- mix paragraphs (the default) with the occasional short list when\n"
            "  it earns its keep. don't list everything.\n"
            "- close on a thought, not a CTA. no 'try X today!'.\n\n"
            "VOICE (this is the hard part):\n"
            "- candid: admit what's uncertain, surprising, or annoying. real\n"
            "  founders don't pretend everything is figured out.\n"
            "- humorous: dry asides, well-placed deadpan. one wink per ~200 words\n"
            "  is the right dose. forced jokes are worse than no jokes.\n"
            "- specific: name companies, prices, dates, code, numbers. 'most\n"
            "  startups' is boring; 'a YC W24 SaaS i talked to last month' is alive.\n"
            "- aware: reference the actual current moment when relevant.\n\n"
            "SEO (light hand):\n"
            "- weave each keyword in 1-3 times max, only where it fits. no stuffing.\n"
            "- the H1 contains the primary keyword if it doesn't fight the headline.\n\n"
            f"LENGTH: hit ~{length} words ±20%. don't pad.\n\n"
        )
        if has_context:
            system += (
                "CURRENT CONTEXT (use this — it's why this article is timely):\n"
                "- weave 2-4 of these findings into the post.\n"
                "- when you use one, attribute it inline: '(Stratechery, Mar 2026)',\n"
                "  '(per The Verge)', etc. plain prose attribution, no footnotes.\n"
                "- don't dump them all in one paragraph. spread them.\n"
                "- if a finding contradicts the article's thesis, address it directly.\n\n"
                f"FINDINGS:\n{current_context.strip()[:4000]}\n\n"
            )
        else:
            system += (
                "NOTE: no current_context was provided. consider whether the topic\n"
                "would benefit from a quick web_search/news_search before drafting —\n"
                "if so, return now and gather sources first. otherwise proceed but\n"
                "rely on durable observations, not stale claims about 'recent trends'.\n\n"
            )
        system += (
            HUMAN_TONE_RULES
            + "\n\n" + STRICT_OUTPUT_RULES
            + ("\n\n" + _brand_voice_block(bv) if bv else "")
            + _ground()
        )
        user = (
            f"topic: {topic}\n"
            f"target keywords: {kw}\n"
            f"target length: ~{length} words\n"
            "write the full article now in markdown. start with the H1."
        )
        body = await _draft_with_llm(
            llm, system=system, user=user, temperature=0.82, max_tokens=4000
        )
        # long-form is the most generic-prone — run the grounded critic over it
        from ..strategy_core import critique_revise

        body = await critique_revise(
            llm, kind="blog article", draft=body, brain=store.get_product_brain(project_id)
        )
        action_id = await _save_action(
            "article",
            title=topic[:120],
            content=body,
            context={
                "target_keywords": target_keywords,
                "target_length": length,
                "had_current_context": has_context,
            },
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
