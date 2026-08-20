"""Small, evidence-driven entity resolver for brand/search candidates.

This is deliberately not a general NER system. It resolves a product's own
mentions using strong identifiers first, a small set of product/category
signals second, and an LLM only for the remaining ambiguous candidates.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from .text import parse_json_lenient

if TYPE_CHECKING:
    from .llm import LLM


_TALLY_CONFLICTS = {
    "strong_identifiers": (
        "tally.so",
        "tallysolutions.com",
        "meettally.com",
    ),
    "negative_phrases": (
        "tally forms",
        "form builder",
        "form creator",
        "online forms",
        "no-code forms",
        "form submissions",
        "payment forms",
        "ai forms",
        "surveys",
        "tallyprime",
        "tally solutions",
        "tally erp",
        "gst software",
        "debt consolidation",
        "credit card debt",
    ),
}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _host(value: str) -> str:
    raw = value if "://" in value else f"https://{value}"
    return (urlparse(raw).hostname or "").lower().removeprefix("www.")


def _urls(value: Any) -> list[str]:
    return re.findall(r"https?://[^\s)]+", json.dumps(value, ensure_ascii=False))


def build_entity_profile(project: dict[str, Any], brain: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the canonical identity from the project's actual public assets."""
    name = str(project.get("name") or "").strip()
    name_norm = _norm(name)
    official_url = str(project.get("url") or "").strip()
    domains = {_host(official_url)} if official_url else set()
    identifiers: set[str] = set()
    app_store_ids: set[str] = set()

    for url in _urls(project.get("brief")) + _urls(project.get("description")):
        host = _host(url)
        if host in {"apps.apple.com", "play.google.com"}:
            m = re.search(r"(?:[?&]id=|/id)([a-z0-9.]+)", url, re.IGNORECASE)
            if m:
                identifier = m.group(1).lower()
                identifiers.add(identifier)
                if identifier.isdigit():
                    app_store_ids.add(identifier)
        elif host:
            domains.add(host)

    # The Android package and iOS listing are part of the brief's public assets
    # for Tally. Keep the fallback scoped to this verified project identity.
    if name_norm == "tally" and "tally-rcuadrado.vercel.app" in domains:
        identifiers.update({"com.rcuadrado.tally", "6768200630"})

    category = _norm((brain or {}).get("category"))
    one_liner = _norm((brain or {}).get("one_liner"))
    description = _norm(project.get("description"))
    positive_phrases: set[str] = set()
    if name_norm == "tally":
        positive_phrases.update({
            "expense tracker",
            "expense tracking",
            "personal finance app",
            "personal finance",
            "control de gastos",
            "shared expenses",
            "shared accounts",
            "manual entry",
            "spending",
            "budgeting",
            "expenses",
            "gastos",
        })
    for phrase in (category, one_liner, description):
        if "expense" in phrase or "gasto" in phrase or "personal finance" in phrase:
            positive_phrases.update({"expense tracker", "personal finance app", "expenses"})

    negative_phrases: set[str] = set()
    negative_identifiers: set[str] = set()
    if name_norm == "tally":
        negative_identifiers.update(_TALLY_CONFLICTS["strong_identifiers"])
        negative_phrases.update(_TALLY_CONFLICTS["negative_phrases"])

    return {
        "entity": (
            f"{name_norm.replace(' ', '_')}_expense_tracker"
            if name_norm == "tally"
            else f"{name_norm.replace(' ', '_')}_product" if name_norm else "product"
        ),
        "name": name,
        "official_url": official_url,
        "description": str(project.get("description") or ""),
        "official_domains": sorted(d for d in domains if d),
        "strong_identifiers": sorted(identifiers),
        "app_store_ids": sorted(app_store_ids),
        "positive_phrases": sorted(positive_phrases),
        "negative_identifiers": sorted(negative_identifiers),
        "negative_phrases": sorted(negative_phrases),
    }


def _candidate_text(item: dict[str, Any]) -> str:
    return _norm(" ".join(
        str(item.get(k) or "") for k in ("title", "url", "snippet", "body", "extra")
    ))


def deterministic_entity_check(item: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Classify obvious cases without spending an LLM call."""
    text = _candidate_text(item)
    name = _norm(profile.get("name"))
    entity = profile.get("entity") or "product"

    exact = [
        signal for signal in [
            *profile.get("strong_identifiers", []),
            *profile.get("official_domains", []),
        ]
        if signal and signal in text
    ]
    if exact:
        return {
            "decision": "accept",
            "entity": entity,
            "confidence": 0.99,
            "reason": f"exact official identifier: {exact[0]}",
        }

    wrong = [
        signal for signal in [
            *profile.get("negative_identifiers", []),
            *profile.get("negative_phrases", []),
        ]
        if signal and signal in text
    ]
    if wrong:
        return {
            "decision": "reject",
            "entity": "other_tally" if name == "tally" else "other_entity",
            "confidence": 0.98 if wrong[0] in profile.get("negative_identifiers", []) else 0.96,
            "reason": f"conflicting identity signal: {wrong[0]}",
        }

    # A traction candidate must contain the product name unless it carries an
    # official identifier. This prevents a broad category result becoming a
    # brand mention merely because the query used the product name.
    if name and not re.search(rf"\b{re.escape(name)}\b", text):
        return {
            "decision": "reject",
            "entity": "unknown",
            "confidence": 0.9,
            "reason": "result does not mention the product name or an official identifier",
        }

    phrase_hits = [p for p in profile.get("positive_phrases", []) if p and p in text]
    strong_category_hits = [
        p for p in phrase_hits
        if p in {"expense tracker", "expense tracking", "personal finance app", "control de gastos"}
    ]
    if (strong_category_hits or len(phrase_hits) >= 2) and name:
        return {
            "decision": "accept",
            "entity": entity,
            "confidence": 0.86 if len(phrase_hits) == 1 else 0.91,
            "reason": f"product name plus category signal: {(strong_category_hits or phrase_hits)[0]}",
        }

    return {
        "decision": "ambiguous",
        "entity": "unknown",
        "confidence": 0.5,
        "reason": "shared product name without a verified identifier or clear category signal",
    }


_ENTITY_SYSTEM = """\
You resolve whether search candidates refer to the specific product described
below. Do not infer identity from a shared name alone. Tally expense tracker
must not be confused with Tally.so/Tally Forms, Tally Solutions/TallyPrime,
debt-consolidation Tally, or ordinary uses of the word tally.

Return STRICT JSON only, an array in the same order as the candidates:
[
  {
    "id": "<candidate id>",
    "is_relevant": true | false,
    "confidence": 0.0,
    "entity": "<canonical entity>|other_tally|unknown",
    "reason": "<short diagnostic reason>"
  }
]

Rules:
- Exact official domains, app package IDs, App Store IDs, or official URL are
  decisive positive evidence.
- A generic word match is not a mention of our product.
- Generic finance words are not enough to identify our app.
- If evidence is insufficient, set is_relevant=false, entity=unknown, and use
  a confidence below 0.7. Never guess.
"""


async def resolve_ambiguous(
    llm: LLM,
    *,
    profile: dict[str, Any],
    items: list[dict[str, Any]],
    source: str,
) -> dict[str, dict[str, Any]]:
    from .llm import Message

    if not items:
        return {}
    payload = [
        {
            "id": str(item.get("id") or i),
            "title": str(item.get("title") or "")[:240],
            "url": str(item.get("url") or "")[:300],
            "snippet": str(item.get("snippet") or item.get("body") or "")[:600],
            "extra": str(item.get("extra") or "")[:180],
        }
        for i, item in enumerate(items)
    ]
    user = (
        f"OUR PRODUCT: {profile.get('name')}\n"
        f"CANONICAL ENTITY: {profile.get('entity')}\n"
        f"OFFICIAL URL: {profile.get('official_url')}\n"
        f"OFFICIAL DOMAINS: {', '.join(profile.get('official_domains') or [])}\n"
        f"STRONG IDENTIFIERS: {', '.join(profile.get('strong_identifiers') or [])}\n"
        f"DESCRIPTION: {profile.get('description') or 'personal expense tracking app'}\n"
        f"SOURCE: {source}\n\n"
        f"CANDIDATES:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Classify every candidate. Output only the JSON array."
    )
    try:
        raw = await llm.complete(
            [Message(role="system", content=_ENTITY_SYSTEM), Message(role="user", content=user)],
            temperature=0.0,
            max_tokens=max(700, 180 * len(items)),
            json_mode=True,
        )
    except Exception:
        return {
            str(item.get("id") or i): {
                "decision": "uncertain",
                "entity": "unknown",
                "confidence": 0.4,
                "reason": "LLM disambiguation unavailable",
            }
            for i, item in enumerate(items)
        }

    verdicts = parse_json_lenient(raw)
    if not isinstance(verdicts, list):
        return {
            str(item.get("id") or i): {
                "decision": "uncertain",
                "entity": "unknown",
                "confidence": 0.4,
                "reason": "LLM returned no usable entity verdict",
            }
            for i, item in enumerate(items)
        }

    out: dict[str, dict[str, Any]] = {}
    for verdict in verdicts:
        if not isinstance(verdict, dict) or verdict.get("id") is None:
            continue
        try:
            confidence = max(0.0, min(1.0, float(verdict.get("confidence") or 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        relevant = bool(verdict.get("is_relevant"))
        out[str(verdict["id"])] = {
            "decision": "accept" if relevant and confidence >= 0.7 else "uncertain" if confidence >= 0.4 else "reject",
            "entity": str(verdict.get("entity") or "unknown"),
            "confidence": round(confidence, 2),
            "reason": str(verdict.get("reason") or "")[:240],
        }
    for i, item in enumerate(items):
        out.setdefault(str(item.get("id") or i), {
            "decision": "uncertain",
            "entity": "unknown",
            "confidence": 0.4,
            "reason": "LLM omitted candidate",
        })
    return out
