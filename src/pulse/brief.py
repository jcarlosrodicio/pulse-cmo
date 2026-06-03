"""The marketing brief — the strategic input Pulse can't infer from a crawl.

A first dive used to run on one input: the URL. With no goal, no ICP, no
baseline, and no idea what the founder already tried, every downstream output
was necessarily generic. The brief fixes that: after the recon crawl, Pulse
proposes what it CAN infer (ICP, the likely success metric, a wedge hypothesis)
and asks the founder for the handful of things only they know (the real goal,
the current numbers, what already flopped, the budget). The full dive then runs
with this in context, and every generator reads it.

`infer_brief` proposes; the founder confirms/edits in the UI; nothing here is
treated as ground truth until they do. Fields that genuinely can't be inferred
are left blank on purpose — that's what the founder fills in.
"""

from __future__ import annotations

from typing import Any

import structlog

from .llm import LLM, Message
from .text import parse_json_lenient

log = structlog.get_logger()


# The brief schema. `infer` = Pulse can guess it from the crawl; `ask` = only
# the founder knows, leave blank for them. The frontend renders these as the
# intake form (label + help drive the UI).
BRIEF_FIELDS: list[dict[str, Any]] = [
    {"key": "goal", "ask": True, "label": "90-day goal",
     "help": "The one outcome that means this worked. Be concrete: a number if you can."},
    {"key": "goal_metric", "infer": True, "label": "Success metric",
     "help": "signups | paying_customers | revenue | stars | installs | awareness"},
    {"key": "horizon_days", "infer": True, "label": "Horizon", "help": "30, 60, or 90 days"},
    {"key": "icp", "infer": True, "label": "Ideal customer",
     "help": "Who it's really for, in one sharp sentence. Segment, not 'everyone'."},
    {"key": "not_for", "infer": True, "label": "Explicitly NOT for",
     "help": "Who you are not chasing. Saying no sharpens the message."},
    {"key": "baseline", "ask": True, "label": "Where you are today",
     "help": "Rough current numbers: traffic, signups, paying users, MRR. 'Zero' is a valid answer."},
    {"key": "tried", "ask": True, "label": "What you've already tried",
     "help": "What worked, what flopped. So Pulse doesn't hand you back the thing that died."},
    {"key": "budget", "infer": True, "label": "Ad budget", "help": "0 | small | funded"},
    {"key": "hours_per_week", "ask": True, "label": "Hours/week you can spend", "help": "Be honest."},
    {"key": "can_produce", "infer": True, "label": "You can make",
     "help": "writing, video, design, code — what you can realistically ship."},
    {"key": "off_limits", "ask": True, "label": "Off-limits",
     "help": "Channels or tactics you refuse to use (e.g. no TikTok, no cold email)."},
    {"key": "wedge_hypothesis", "infer": True, "label": "Your wedge",
     "help": "The one thing you want remembered vs the competition. Pulse proposes; you sharpen."},
    {"key": "assets", "ask": True, "label": "Unfair advantages",
     "help": "Existing audience, community, design partners, waitlist, a name people know."},
]


def default_brief() -> dict[str, Any]:
    return {
        "goal": "",
        "goal_metric": "",
        "horizon_days": 90,
        "icp": "",
        "not_for": "",
        "baseline": "",
        "tried": "",
        "budget": "0",
        "hours_per_week": "",
        "can_produce": ["writing"],
        "off_limits": "",
        "wedge_hypothesis": "",
        "assets": "",
    }


_INFER_SYSTEM = """\
You are a growth lead reading a product Pulse just crawled. Propose the brief
fields a sharp analyst could infer, so the founder confirms instead of starting
from a blank form. Answer IMMEDIATELY with ONE JSON object and nothing else — no
reasoning, no preface, no text before or after it. Every key and string value
must be double-quoted.

{
  "goal_metric": "signups|paying_customers|revenue|stars|installs|awareness",
  "horizon_days": 90,
  "icp": "the specific buyer segment, one sentence",
  "not_for": "who this is explicitly not for",
  "budget": "0|small|funded",
  "can_produce": ["writing"],
  "wedge_hypothesis": "one sentence: the thing to be remembered for vs the competitors"
}

Guidance:
- icp is a segment ("indie devs already paying for OpenAI who watch their bill"),
  never "developers" or "everyone".
- wedge_hypothesis is the angle the incumbents do NOT already own — don't just
  restate the product's tagline.
- goal_metric follows the pricing model: paid -> paying_customers, free OSS repo
  -> stars, free app -> installs, otherwise signups.
- Default budget "0" and can_produce ["writing"] for an indie unless the crawl
  says otherwise. Ground every value in the crawl.\
"""


async def infer_brief(
    llm: LLM,
    *,
    project: dict[str, Any],
    product_md: str = "",
    crawl_text: str = "",
) -> dict[str, Any]:
    """Propose the inferable brief fields from the crawl + product doc.

    Returns a full brief dict (default_brief merged with the inferred values).
    The ask-only fields (goal, baseline, tried, hours, off_limits, assets) stay
    blank for the founder to fill.
    """
    base = default_brief()
    competitors = ", ".join(project.get("competitors") or []) or "(none known)"
    user = (
        f"PRODUCT: {project.get('name')} ({project.get('url')})\n"
        f"DESCRIPTION: {project.get('description') or '(none)'}\n"
        f"COMPETITORS: {competitors}\n"
    )
    if crawl_text:
        user += f"\nWHAT THE SITE ACTUALLY SAYS (crawled):\n{crawl_text[:2000]}\n"
    if product_md:
        user += f"\nPRODUCT INFORMATION:\n{product_md[:1200]}\n"
    user += "\nOutput only the JSON object now."

    # ONE call. This runs in the BACKGROUND (via /brief/suggest) so it doesn't
    # block the modal — which means we can give a reasoning model (MiniMax M2.x)
    # enough token budget to finish thinking AND emit the JSON. Too small a cap
    # and it spends the whole budget reasoning and returns nothing usable.
    try:
        raw = await llm.complete(
            [Message(role="system", content=_INFER_SYSTEM), Message(role="user", content=user)],
            temperature=0.4,
            max_tokens=1500,
        )
    except Exception as e:
        log.warning("infer_brief_failed", error=repr(e))
        return base
    parsed = parse_json_lenient(raw)
    if isinstance(parsed, dict):
        for k in ("goal_metric", "horizon_days", "icp", "not_for", "budget",
                  "can_produce", "wedge_hypothesis"):
            v = parsed.get(k)
            if v not in (None, "", "unknown", []):
                base[k] = v
    return base


def brief_context_block(brief: dict[str, Any] | None) -> str:
    """Render the brief as a compact context block for run/generator prompts.
    Returns '' if there's no meaningful brief yet."""
    if not brief:
        return ""
    rows: list[str] = []
    label = {f["key"]: f["label"] for f in BRIEF_FIELDS}
    for key in ("goal", "goal_metric", "horizon_days", "icp", "not_for", "baseline",
                "tried", "budget", "hours_per_week", "can_produce", "off_limits",
                "wedge_hypothesis", "assets"):
        v = brief.get(key)
        if v in (None, "", [], "0"):
            continue
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        rows.append(f"  {label.get(key, key)}: {v}")
    if not rows:
        return ""
    return "MARKETING BRIEF (the founder's stated goal + constraints — optimize for THIS):\n" + "\n".join(rows)
