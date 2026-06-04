"""Reddit discovery + reply drafting.

Read-only — no posting. Uses Reddit's public JSON endpoints (no auth needed).
For copy-paste only; the user posts from their own account.

DISCOVERY PIPELINE (v2):

  Stage 1: PROFILE       LLM extracts pain_points + audience + use_cases from
                          name+desc+competitors. Per-run, ~1 cheap call.

  Stage 2: QUERY PLAN    LLM generates 18-24 queries grouped by intent type
                          (pain / switching / shopping / comparison / question).

  Stage 3: SEARCH        Fan-out to old.reddit.com across N queries × M subs.
                          Filters: deleted, removed, locked, self-promo,
                          NSFW, too old, our own product mention.

  Stage 4: REGEX SCORE   Cheap pattern scoring (switching intent, frustration,
                          shopping, etc.). Drops score < 0. Top 20 advance.

  Stage 5: LLM VERIFY    THE KEY UPGRADE. Single batched call asks the model:
                          "For each post, score 0-100 on whether this person
                          has a problem our product genuinely solves, and
                          recommend the reply angle." Drops semantic noise.

  Stage 6: RANK + RETURN  final_score = regex*0.35 + llm*0.65. Top 10 are
                          returned with `suggested_angle`, `mention_product`,
                          `reason` — the agent uses these as input to
                          draft_reddit_reply.

Reply drafting follows the spec's anti-spam rules:
  * lead with 5+ sentences of actual value
  * mention product only if it genuinely fits
  * match subreddit tone
  * avoid AI tells (em-dashes, "I'd love to", "happy to help", etc.)
  * second LLM pass to "humanize" the draft
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone

import httpx
import structlog

from ..llm import LLM, Message
from ..store import ActionStore
from ..text import strip_draft_preamble, strip_reasoning
from .registry import Tool, tool

log = structlog.get_logger()

REDDIT_HEADERS = {
    # Reddit's www host now 403s anonymous bot UAs aggressively. The old.reddit
    # / api.reddit hosts still serve the public search JSON with browser-style
    # UAs. ASCII-only — non-ASCII characters in headers raise UnicodeEncodeError.
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# Hosts to try in order. If the first returns a non-200, we fall through to the
# next. `old.reddit.com` is the most reliable since Reddit gates the rewrite to
# new.reddit far more strictly.
REDDIT_HOSTS = ["https://old.reddit.com", "https://api.reddit.com"]

HUMANIZE_RULES = """\
Rewrite the reply so it sounds unmistakably like a real person typing on their
phone between meetings. Small character energy. NOT an AI being helpful.

HARD BANS (remove every instance):
- em-dashes (—). use periods or commas or a new sentence.
- emojis. all of them. even subtle ones.
- "I'd love to", "happy to help", "let me know if you have questions",
  "I hope this helps", "feel free to", "as an AI", "delve into", "navigate",
  "in this digital age", "in today's world", "tapestry", "leverage",
  "synergy", "robust", "comprehensive", "seamless", "empower", "supercharge".
- closing sign-offs: "hope that helps!", "best of luck!", "good luck!",
  "let me know how it goes!".
- "great question!" / "interesting point!" / any compliment-the-poster opener.
- the word "literally" unless something literally is the case.

VOICE (positive direction):
- contractions everywhere. "we're", "i'm", "don't", "y'know", "kinda".
- lowercase first letters are fine. fragments are fine. one-line replies are fine.
- vary sentence length. punchy. longer thought. punchy.
- concrete > abstract. a specific tool name, number, or date beats "various options".
- show your work where it helps but don't lecture. one example > three.
- if you've actually done the thing, say so. "did this at my last gig" beats
  "many people find that...".
- mild self-deprecation is fine. "i made this mistake too".

LENGTH:
- keep roughly the same length. don't pad. don't add new claims.
- if the original is too long for the question, trim ruthlessly.

OUTPUT:
- output ONLY the rewritten reply text. no preface, no quotes, no explanation.\
"""


async def _search_reddit(query: str, subreddit: str | None = None, sort: str = "new", limit: int = 10) -> list[dict]:
    """Search Reddit using the public search JSON endpoint.

    Tries each host in REDDIT_HOSTS until one returns 200. Reddit's www host
    aggressively 403s anonymous traffic, but old.reddit.com still serves the
    same JSON. Errors are swallowed and logged — the caller gets [].
    """
    sub = (subreddit or "").lstrip("r/").lstrip("/") if subreddit else None
    params = {"q": query, "sort": sort, "limit": str(limit), "t": "month"}
    if sub:
        params["restrict_sr"] = "on"

    last_status: int | None = None
    last_err: str | None = None
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for host in REDDIT_HOSTS:
            url = f"{host}/r/{sub}/search.json" if sub else f"{host}/search.json"
            try:
                r = await client.get(url, headers=REDDIT_HEADERS, params=params)
            except Exception as e:
                last_err = repr(e)
                continue
            if r.status_code == 200:
                try:
                    data = r.json()
                except Exception as e:
                    last_err = f"json: {e}"
                    continue
                return [c.get("data", {}) for c in (data.get("data") or {}).get("children") or []]
            last_status = r.status_code
            # 429 = rate limited; backing off across hosts is the same as
            # backing off period. 5xx falls through to the next host.
    log.warning(
        "reddit_search_failed",
        query=query,
        sub=subreddit,
        last_status=last_status,
        last_err=last_err,
    )
    return []


_REDDIT_URL_RE = re.compile(r"reddit\.com/r/([^/?#]+)/comments/([a-z0-9]+)", re.I)


async def _search_reddit_websearch(
    base_url: str, api_key: str, query: str, subreddit: str | None = None, n: int = 8
) -> list[dict]:
    """Find Reddit threads via the web-search API (`site:reddit.com …`).

    Reddit network-blocks anonymous JSON from servers (403), so direct search is
    dead. A general web search indexes Reddit well and works server-side. Returns
    raw-post-shaped dicts (so _format_post works); score/comments/created_utc are
    unknown from snippets, so they're left None and the LLM verify does the real
    filtering.
    """
    if not (base_url and api_key):
        return []
    sub = (subreddit or "").lstrip("r/").lstrip("/") if subreddit else None
    sq = f"site:reddit.com/r/{sub} {query}" if sub else f"site:reddit.com {query}"
    try:
        async with httpx.AsyncClient(timeout=25.0) as cx:
            r = await cx.post(
                f"{base_url.rstrip('/')}/v1/tools/search",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"query": sq, "num_results": n},
            )
        if r.status_code >= 400:
            return []
        data = r.json()
    except Exception as e:
        log.warning("reddit_websearch_failed", query=query, error=repr(e))
        return []
    # the search API returns either a bare list or a {results|data|items: [...]} dict
    if isinstance(data, list):
        items = data
    else:
        items = data.get("results") or data.get("data") or data.get("items") or []
        if isinstance(items, dict):
            items = items.get("items") or items.get("results") or []
    out: list[dict] = []
    for it in items or []:
        url = it.get("url") or it.get("link") or ""
        m = _REDDIT_URL_RE.search(url)
        if not m:
            continue
        found_sub, pid = m.group(1), m.group(2)
        title = (it.get("title") or "").strip()
        title = re.sub(r"\s*[:\-|]\s*r/\w+.*$", "", title).strip() or title  # drop " : r/sub" suffix
        snippet = (it.get("snippet") or it.get("description") or it.get("content") or "").strip()
        out.append({
            "id": pid,
            "subreddit": found_sub,
            "title": title,
            "selftext": snippet[:1200],
            "permalink": f"/r/{found_sub}/comments/{pid}/",
            "score": None,
            "num_comments": None,
            "author": None,
            "created_utc": None,  # unknown from a web snippet
        })
    return out


def _format_post(post: dict) -> dict:
    return {
        "id": post.get("id"),
        "subreddit": post.get("subreddit"),
        "title": post.get("title"),
        "selftext": (post.get("selftext") or "")[:1200],
        "url": f"https://www.reddit.com{post.get('permalink', '')}",
        "score": post.get("score"),
        "num_comments": post.get("num_comments"),
        "author": post.get("author"),
        "created_utc": post.get("created_utc"),
        "age_hours": _age_hours(post.get("created_utc")),
        "is_question": _looks_like_question(post.get("title", ""), post.get("selftext", "")),
    }


def _age_hours(created_utc: float | None) -> float | None:
    if not created_utc:
        return None
    return round((datetime.now(timezone.utc).timestamp() - created_utc) / 3600, 1)


def _is_searchable_post(post: dict, product_name: str) -> bool:
    """Filter out posts that can never be a good opportunity to reply on.

    Cheap pre-filter — runs after Reddit returns the raw post, before any
    scoring. Drops: deleted/removed bodies, locked threads, our own product
    mentions, obvious self-promo launches, NSFW/spam.
    """
    if post.get("locked") or post.get("archived"):
        return False
    if post.get("over_18"):       # NSFW
        return False
    selftext = (post.get("selftext") or "").strip().lower()
    if selftext in ("[removed]", "[deleted]"):
        return False
    title = (post.get("title") or "").lower()
    # someone else's launch post
    if title.startswith(("show hn:", "[show]", "[hiring]", "[for hire]", "i made", "i built", "introducing ", "launching ")):
        return False
    # our own product's name in the title — definitely not for us to reply to
    if product_name and product_name.lower() in title:
        return False
    return True


def _looks_like_question(title: str, body: str) -> bool:
    t = (title + " " + (body or "")).lower()
    return (
        "?" in t
        or any(t.startswith(p) for p in ("how do", "how can", "what's", "is there", "anyone know"))
        or any(p in t for p in ("recommend", "alternatives to", "looking for", "suggestions for"))
    )


# Pain-point regex patterns. Higher weight = stronger intent signal.
# These are matched against title+body to score post relevance after fetch.
_INTENT_PATTERNS: list[tuple[str, int]] = [
    # switching intent — gold
    (r"\b(alternative|alternatives) to\b", 40),
    (r"\b(switching|switch|migrate|moving) (away )?from\b", 40),
    (r"\bsomething (better|cheaper) than\b", 35),
    (r"\binstead of\b", 25),
    (r"\breplace(ment)? for\b", 30),
    # frustration — high signal of unmet need
    (r"\b(tired|sick|fed up) of\b", 35),
    (r"\b(hate|hating|frustrated with|annoyed with)\b", 30),
    (r"\b(too expensive|too slow|too complex|too complicated)\b", 30),
    (r"\b(broken|buggy|unreliable|garbage)\b", 20),
    (r"\bcan't (afford|stand)\b", 25),
    # active search — they're shopping right now
    (r"\b(looking for|searching for|need (a|an))\b", 30),
    (r"\b(recommend|recommendation|suggest|suggestions)\b", 25),
    (r"\bwhat (do you|are you|tool|stack) (use|using|recommend)\b", 25),
    (r"\b(best|top) (tool|tools|app|apps|service|services|option)\b", 20),
    # comparison / decision
    (r"\b(\w+)\s+vs\.?\s+(\w+)\b", 20),
    (r"\bworth (it|switching)\b", 15),
    (r"\bopinions on\b", 15),
    # question shape
    (r"\?", 10),
    (r"^(how do|how can|why is|why does|what's the|is there a)\b", 15),
]


def _intent_score(post: dict) -> int:
    haystack = (post.get("title", "") + "\n" + (post.get("selftext", "") or "")).lower()
    score = 0
    matched: list[str] = []
    for pat, weight in _INTENT_PATTERNS:
        m = re.search(pat, haystack, flags=re.IGNORECASE)
        if m:
            score += weight
            matched.append(m.group(0))
    # engagement multiplier — a single comment beats zero, but very high
    # comment counts often mean the question is already answered
    num_comments = int(post.get("num_comments") or 0)
    if num_comments == 0:
        score += 8           # virgin thread, you can be the first useful reply
    elif num_comments < 5:
        score += 5
    elif num_comments < 20:
        score += 2
    else:
        score -= 5           # saturated
    # recency bonus
    age_h = post.get("age_hours") or 0
    if age_h < 6:
        score += 15
    elif age_h < 24:
        score += 10
    elif age_h < 72:
        score += 5
    return score


_DEFAULT_BROAD_SUBS = [
    "SaaS",
    "SideProject",
    "indiehackers",
    "Entrepreneur",
    "smallbusiness",
    "startups",
]


# ---------------------------------------------------------------------------
# STAGE 5: LLM VERIFY — semantic relevance check (the key upgrade).
# ---------------------------------------------------------------------------

_VERIFY_PROMPT = """\
You are filtering Reddit threads for a marketing team. For each post, decide:

  1. Is this person actually expressing a problem this product helps with?
     (NOT just a keyword match — does it semantically fit?)
  2. What's the best REPLY ANGLE — what should we focus on?
  3. Should we mention the product, or just be helpful with no mention?

Output STRICT JSON only — an array of objects, one per input post, IN THE
SAME ORDER as the input. No preamble, no commentary, no code fences:

[
  {
    "id": "<the post id from the input>",
    "score": 0-100,
    "mention_product": true | false,
    "angle": "<one short sentence — the reply strategy>",
    "reason": "<one short sentence — why this score>"
  },
  ...
]

Score guide (be strict — there's no prize for false positives):
  90-100  Bull's-eye. They're literally asking for what we offer.
  70-89   Adjacent. Product mention works if framed as 'I built this for X'.
  50-69   Tangential. Helpful comment, NO product mention.
  30-49   Weak match. Maybe a one-liner, probably skip.
  0-29    Not relevant. Filter out — we won't comment.

Rules:
- Be skeptical. Reddit search is noisy — most candidates are 0-49.
- Threads that mention competitors directly score higher than category posts.
- Threads where the OP is venting (no question) score lower than active questions.
- Old threads (mentioned in the metadata) score lower; freshness matters.
- DISQUALIFIERS in the profile are an instant 0-29.
- Output ONLY the JSON array. First character is '['.\
"""


async def _verify_relevance(
    llm: LLM,
    *,
    product_name: str,
    product_desc: str,
    profile: dict,
    posts: list[dict],
) -> dict[str, dict]:
    """Stage 5 — batched semantic relevance scoring.

    Returns a dict keyed by post id with the LLM's verdict. Posts the LLM
    omits are dropped from the final ranking; posts the LLM includes that
    aren't in the input are ignored.
    """
    if not posts:
        return {}

    # Compact payload — the LLM only needs title + body snippet + age.
    items: list[dict] = []
    for p in posts:
        items.append({
            "id": p["id"],
            "subreddit": p.get("subreddit"),
            "title": p.get("title") or "",
            "body": (p.get("selftext") or "")[:500],
            "age_hours": p.get("age_hours"),
            "num_comments": p.get("num_comments"),
        })

    user = (
        f"PRODUCT: {product_name}\n"
        f"WHAT IT DOES: {product_desc}\n"
        f"PAIN POINTS WE SOLVE: {', '.join(profile.get('pain_points') or []) or '(none)'}\n"
        f"AUDIENCE: {', '.join(profile.get('audience') or [])}\n"
        f"DISQUALIFIERS (instant low score): "
        f"{', '.join(profile.get('disqualifiers') or []) or '(none)'}\n\n"
        f"POSTS TO SCORE ({len(items)}):\n"
        f"{json.dumps(items, ensure_ascii=False)}\n\n"
        "Score each one. Output the JSON array."
    )
    try:
        raw = await llm.complete(
            [Message(role="system", content=_VERIFY_PROMPT), Message(role="user", content=user)],
            temperature=0.3,
            max_tokens=2500,
        )
    except Exception as e:
        log.warning("reddit_verify_failed", error=repr(e))
        return {}

    parsed = _parse_json_object(raw)
    if not isinstance(parsed, list):
        return {}

    out: dict[str, dict] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        pid = item.get("id")
        if not pid:
            continue
        try:
            score = max(0, min(100, int(item.get("score") or 0)))
        except (ValueError, TypeError):
            score = 0
        out[str(pid)] = {
            "llm_score": score,
            "mention_product": bool(item.get("mention_product")),
            "suggested_angle": str(item.get("angle") or "")[:240],
            "llm_reason": str(item.get("reason") or "")[:240],
        }
    return out


# ---------------------------------------------------------------------------
# STAGE 1: PROFILE — turn raw product context into a structured profile.
# ---------------------------------------------------------------------------

_PROFILE_PROMPT = """\
You are a product analyst. Given a product description, extract a structured
profile we'll use to find Reddit threads where this product genuinely belongs
in the conversation.

Output STRICT JSON only, no preamble, no code fences, no commentary:

{
  "pain_points": ["short phrase", ...],          // 3-6 real frustrations
                                                  // the audience has TODAY
                                                  // that this product fixes
  "audience": ["who they are", ...],              // 2-4 audience archetypes,
                                                  // each a short phrase
                                                  // ('indie founders',
                                                  // 'solo SaaS engineers')
  "use_cases": ["the user is trying to ...", ..], // 3-5 concrete jobs-to-be-done
  "category_terms": ["term", ...],                // 3-6 how outsiders refer to
                                                  // this product category
                                                  // (no marketing words)
  "disqualifiers": ["term", ...]                  // 0-3 audience types we
                                                  // explicitly do NOT target
                                                  // (e.g. 'enterprise teams')
}

Rules:
- Be SPECIFIC. "fast" is bad; "tired of waiting 4s for model responses" is good.
- Use ACTUAL competitor names from the input, not generic 'competitors'.
- Pain points should be things real humans actually complain about on Reddit.
- Output ONLY the JSON object. The first character of your response is '{'.\
"""


_QUERY_PLAN_PROMPT = """\
You generate Reddit search queries that find threads where someone is
ALREADY EXPRESSING the pain points or shopping intent below — without naming
our product.

The goal is to surface posts like:
  * "tired of <competitor>" (frustration)
  * "<competitor> is too expensive" (cost gripe)
  * "alternative to <competitor>" (switching intent)
  * "best API for <category use-case>" (active shopping)
  * "anyone else hate paying $20/mo for <competitor>?" (pricing anger)

Output STRICT JSON only, no preamble:

{
  "pain":       ["query1", "query2", ...],      // 4-5 queries
  "switching":  ["query1", "query2", ...],      // 4-5 queries
  "shopping":   ["query1", "query2", ...],      // 4-5 queries
  "comparison": ["query1", "query2", ...],      // 3-4 queries
  "question":   ["query1", "query2", ...]       // 3-4 queries
}

Rules:
- Each query 2-7 words. Reddit's search is dumb; short, crisp wins.
- Use REAL competitor names from the input. Don't generalize.
- Don't include OUR product's name in any query.
- No emojis. No quotation marks. Lowercase preferred.
- Output ONLY the JSON object. First character is '{'.\
"""


async def _build_profile(
    llm: LLM,
    *,
    product_name: str,
    product_desc: str,
    competitors: list[str],
) -> dict:
    """Stage 1 — structured profile from raw product context."""
    user = (
        f"PRODUCT: {product_name}\n"
        f"WHAT IT DOES: {product_desc or '(no description provided)'}\n"
        f"KNOWN COMPETITORS: {', '.join(competitors) or '(none yet)'}\n\n"
        "Build the profile now. Output only the JSON object."
    )
    fallback = {
        "pain_points": [],
        "audience": [],
        "use_cases": [],
        "category_terms": [],
        "disqualifiers": [],
    }
    try:
        raw = await llm.complete(
            [Message(role="system", content=_PROFILE_PROMPT), Message(role="user", content=user)],
            temperature=0.6,
            max_tokens=900,
        )
    except Exception as e:
        log.warning("reddit_profile_failed", error=repr(e))
        return fallback
    return _parse_json_object(raw) or fallback


async def _plan_queries(
    llm: LLM,
    *,
    product_name: str,
    product_desc: str,
    competitors: list[str],
    profile: dict,
) -> dict[str, list[str]]:
    """Stage 2 — structured query plan grouped by intent type."""
    user = (
        f"PRODUCT: {product_name}\n"
        f"WHAT IT DOES: {product_desc}\n"
        f"COMPETITORS: {', '.join(competitors) or '(none)'}\n"
        f"PAIN POINTS: {', '.join(profile.get('pain_points') or []) or '(none extracted)'}\n"
        f"AUDIENCE: {', '.join(profile.get('audience') or [])}\n"
        f"USE CASES: {', '.join(profile.get('use_cases') or [])}\n"
        f"CATEGORY TERMS: {', '.join(profile.get('category_terms') or [])}\n\n"
        "Generate the query plan now. Output only the JSON object."
    )
    try:
        raw = await llm.complete(
            [Message(role="system", content=_QUERY_PLAN_PROMPT), Message(role="user", content=user)],
            temperature=0.85,
            max_tokens=1200,
        )
    except Exception as e:
        log.warning("reddit_query_plan_failed", error=repr(e))
        return {}

    plan = _parse_json_object(raw) or {}
    cleaned: dict[str, list[str]] = {}
    for kind in ("pain", "switching", "shopping", "comparison", "question"):
        items = plan.get(kind) or []
        norm: list[str] = []
        seen: set[str] = set()
        for q in items:
            if not isinstance(q, str):
                continue
            q = re.sub(r'^[\d\.\-\*\)\s]+', '', q).strip().strip('"').strip("'")
            if not q or len(q.split()) > 10:
                continue
            if product_name and product_name.lower() in q.lower():
                continue
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            norm.append(q)
        cleaned[kind] = norm[:6]
    return cleaned


def _parse_json_object(raw: str) -> dict | None:
    """Best-effort JSON parser — tolerates code-fence wrapping and tail noise."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        # strip a leading ```json / ``` fence
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    # find the outermost {...} or [...]
    m = re.search(r"\{.*\}|\[.*\]", s, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def make_reddit_tools(
    llm: LLM,
    store: ActionStore,
    project_id: int,
    run_id: int,
    web_base_url: str = "",
    web_api_key: str = "",
) -> list[Tool]:
    """Build Reddit tools bound to a run for persistence side-effects.

    Reddit search goes through the web-search API (`site:reddit.com`) because
    Reddit blocks anonymous server access; web_base_url/web_api_key power that.
    """

    @tool
    async def find_reddit_opportunities(
        seed_keywords: list[str] = [],
        subreddits: list[str] = [],
        days_back: int = 14,
    ) -> str:
        """Find Reddit threads where the product is genuinely relevant.

        Six-stage pipeline:
          1) PROFILE     — LLM extracts pain points + audience from product
          2) QUERY PLAN  — LLM generates intent-grouped queries
          3) SEARCH      — fan-out across Reddit (queries × subs)
          4) REGEX SCORE — cheap intent-pattern scoring; top 20 advance
          5) LLM VERIFY  — semantic relevance check (the key upgrade)
          6) RANK        — combined regex + LLM score; return top 10
            enriched with `suggested_angle` and `mention_product`
            so the agent can draft a precise reply.

        Run this AT MOST ONCE per agent run. Use the `suggested_angle` from
        each returned post when calling draft_reddit_reply.

        Args:
            seed_keywords: Optional hints. Usually leave empty — queries are
                generated entirely from project context + competitors.
            subreddits: Optional priority subreddits to search alongside the
                global feed. Defaults to indie-founder subs.
            days_back: Recency window (default 14, max 30).
        """
        days_back = max(1, min(int(days_back), 30))
        cutoff = (datetime.now(timezone.utc).timestamp() - days_back * 86400)

        project = store.get_project(project_id) or {}
        product_name = project.get("name", "") or ""
        product_desc = project.get("description", "") or ""
        competitors = project.get("competitors") or []

        wi = (project.get("writing_instructions") or {})
        reddit_wi = wi.get("reddit") or {}
        wi_subs = reddit_wi.get("subreddits") or []
        wi_kws = reddit_wi.get("keywords") or []
        merged_subs = list(dict.fromkeys(
            [s.lstrip("r/").lstrip("/") for s in (subreddits + wi_subs) if s.strip()]
        )) or list(_DEFAULT_BROAD_SUBS)
        merged_seeds = list(dict.fromkeys(seed_keywords + wi_kws))

        # ---------- STAGE 1: PROFILE ----------
        profile = await _build_profile(
            llm,
            product_name=product_name,
            product_desc=product_desc,
            competitors=competitors,
        )
        log.info(
            "reddit_profile",
            pain=len(profile.get("pain_points") or []),
            audience=len(profile.get("audience") or []),
        )

        # ---------- STAGE 2: QUERY PLAN ----------
        plan = await _plan_queries(
            llm,
            product_name=product_name,
            product_desc=product_desc,
            competitors=competitors,
            profile=profile,
        )
        # Flatten plan into a single list, preserving order by intent priority.
        # Pain + switching first (highest-intent), then shopping, comparison, question.
        ordered: list[str] = []
        for kind in ("pain", "switching", "shopping", "comparison", "question"):
            ordered.extend(plan.get(kind) or [])
        # If the LLM bailed entirely, fall back to seed keywords + competitor pain.
        if not ordered:
            ordered = merged_seeds or [f"alternative to {c}" for c in competitors[:5]]

        log.info(
            "reddit_query_plan",
            n_queries=len(ordered),
            by_kind={k: len(plan.get(k) or []) for k in ("pain", "switching", "shopping", "comparison", "question")},
            sample=ordered[:5],
        )

        # ---------- STAGE 3: SEARCH (via web search — Reddit blocks anon servers) ----------
        # Fewer, higher-quality queries with BOUNDED concurrency — the search
        # provider throttles a big concurrent fan-out down to empty results.
        sem = asyncio.Semaphore(4)

        async def _bounded(q: str, sub: str | None, n: int) -> list[dict]:
            async with sem:
                return await _search_reddit_websearch(web_base_url, web_api_key, q, sub, n)

        tasks: list = []
        for q in ordered[:8]:
            tasks.append(_bounded(q, None, 8))
        for q in ordered[:3]:
            for sub in merged_subs[:2]:
                tasks.append(_bounded(q, sub, 6))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        name_l = product_name.lower()
        seen: dict[str, dict] = {}
        for batch in results:
            if isinstance(batch, Exception):
                continue
            for post in batch:
                pid = post.get("id")
                if not pid or pid in seen:
                    continue
                cu = post.get("created_utc")
                if cu and cu < cutoff:  # web snippets have no timestamp → keep them
                    continue
                # skip threads already about our own product (we reply, not self-promote)
                blob = f"{post.get('title','')} {post.get('selftext','')}".lower()
                if name_l and name_l in blob:
                    continue
                seen[pid] = _format_post(post)

        # ---------- STAGE 4: REGEX SCORE ----------
        candidates = list(seen.values())
        for p in candidates:
            p["regex_score"] = _intent_score(p)
        # Drop strongly negative posts immediately (saturated launch posts, etc.)
        candidates = [p for p in candidates if p["regex_score"] > -5]
        candidates.sort(key=lambda p: (-p["regex_score"], -(p.get("created_utc") or 0)))
        top_for_verify = candidates[:20]
        log.info(
            "reddit_regex_filter",
            total=len(seen),
            after_regex=len(candidates),
            verifying=len(top_for_verify),
        )

        # ---------- STAGE 5: LLM VERIFY ----------
        if top_for_verify:
            verdicts = await _verify_relevance(
                llm,
                product_name=product_name,
                product_desc=product_desc,
                profile=profile,
                posts=top_for_verify,
            )
        else:
            verdicts = {}

        # ---------- STAGE 6: RANK + RETURN ----------
        # Two-tier so a niche product is never left with nothing: score every
        # verified candidate; surface the reply-worthy ones (>= SURFACE), and if
        # none clear the bar, surface the single best as a labelled "watchlist"
        # item (still human-reviewed, mention_product stays strict). Genuine
        # garbage (< WATCH_MIN) is still dropped.
        SURFACE, WATCH_MIN = 45, 25
        scored: list[dict] = []
        for p in top_for_verify:
            v = verdicts.get(p["id"])
            if not v:
                continue
            regex_norm = max(0, min(100, p["regex_score"]))
            combined = 0.35 * regex_norm + 0.65 * v["llm_score"]
            scored.append({
                **p,
                "selftext": (p.get("selftext") or "")[:500],
                **v,
                "final_score": round(combined, 1),
            })
        scored.sort(key=lambda p: (-p["llm_score"], -p["final_score"]))
        enriched = [p for p in scored if p["llm_score"] >= SURFACE]
        if not enriched and scored and scored[0]["llm_score"] >= WATCH_MIN:
            best = dict(scored[0])
            best["watchlist"] = True
            enriched = [best]
        enriched.sort(key=lambda p: -p["final_score"])
        top = enriched[:10]
        log.info(
            "reddit_pipeline_done",
            verified=len(enriched),
            returned=len(top),
        )

        return json.dumps(
            {
                "ok": True,
                "found": len(top),
                "candidates_searched": len(seen),
                "candidates_verified": len(top_for_verify),
                "profile": {
                    "pain_points": profile.get("pain_points") or [],
                    "audience": profile.get("audience") or [],
                },
                "queries_by_kind": plan,
                "subs_searched": merged_subs[:4],
                "items": top,
            },
            ensure_ascii=False,
        )[:14000]

    @tool
    async def draft_reddit_reply(
        post_url: str,
        post_title: str,
        post_body: str,
        subreddit: str,
        product_angle: str = "",
        why_relevant: str = "",
        mention_product: bool = True,
    ) -> str:
        """Draft three reply variants for a Reddit thread.

        Use AFTER find_reddit_opportunities surfaced a relevant thread you
        read in full. Pass `product_angle` and `why_relevant` straight from
        the verification result. The tool produces 3 variants (each takes a
        different angle), humanizes each, and scrubs AI tells. Saves a copy-
        paste action; no auto-post.

        Args:
            post_url: Direct Reddit thread URL.
            post_title: Title of the post we're replying to.
            post_body: Body text of the post (paste in full).
            subreddit: Subreddit name (without r/).
            product_angle: Reply-strategy hint, usually the verifier's
                `suggested_angle`. Tells variants what to focus on.
            why_relevant: Short sentence on why this thread fits the product.
                Stored on the action so the user sees the context above the
                draft. Often the verifier's `llm_reason`.
            mention_product: If False, all variants are written with NO
                product mention — the agent just helps. Default True.
        """
        bv = store.get_brand_voice(project_id) or {}
        wi = (store.get_project(project_id) or {}).get("writing_instructions") or {}
        reddit_extra = (wi.get("reddit") or {}).get("instructions", "")

        project = store.get_project(project_id) or {}
        product_name = project.get("name", "")
        product_desc = project.get("description", "")

        system = (
            "You draft Reddit replies that look like they were written by a real\n"
            "redditor — a smart founder/engineer who happens to be answering this\n"
            "thread. NOT a product team. The bar is: if a moderator skimmed it,\n"
            "they wouldn't flag it as self-promo.\n\n"
            "STRUCTURE:\n"
            "1. answer the question first. directly. like you would in a DM.\n"
            "   5+ sentences of actual substance. concrete. specific. no preamble.\n"
            "2. only mention the product if it genuinely fits the question. if it\n"
            "   does, frame it as a personal aside: 'i built X for this exact thing'\n"
            "   or 'fwiw i use X for this'. one mention max. one link max.\n"
            "3. if the product DOESN'T fit, write the reply with zero product\n"
            "   mention. just be helpful. that's how trust gets built on reddit.\n\n"
            "VOICE:\n"
            "- founder talking to another founder on a tuesday afternoon.\n"
            "- contractions, lowercase opens, fragments. that's how reddit reads.\n"
            "- short paragraphs. 1-3 sentences each. white space is your friend.\n"
            "- match the subreddit. r/SideProject is forgiving and personal.\n"
            "  r/programming, r/SaaS, r/startups will roast anything that smells\n"
            "  like marketing. tone down the polish. show the warts.\n"
            "- mild self-deprecation lands. 'we got this wrong the first 6 months' >\n"
            "  'we strategically iterated'.\n\n"
            "HARD BANS:\n"
            "- em-dashes (—). emojis. exclamation marks (max one).\n"
            "- 'great question', 'i'd love to', 'happy to help', 'hope this helps',\n"
            "  'feel free to', 'let me know'.\n"
            "- closing sign-offs or CTAs ('check it out', 'dm me').\n"
            "- bullet lists unless the question is literally 'list X'.\n"
            "- saying the product's full name more than once.\n\n"
            f"PRODUCT CONTEXT (use sparingly, only if it ACTUALLY helps the asker):\n"
            f"- Name: {product_name}\n"
            f"- About: {product_desc}\n"
            f"- Subreddit: r/{subreddit}\n"
        )
        if bv.get("tone"):
            system += f"- Author's tone: {bv['tone']}\n"
        if reddit_extra:
            system += f"\nUser's Reddit-specific instructions:\n{reddit_extra}\n"

        # Bias the system prompt based on whether the verifier thinks a
        # product mention belongs in this thread.
        if not mention_product:
            system += (
                "\nIMPORTANT: This thread does NOT warrant a product mention.\n"
                "ALL three variants must be written as a helpful redditor with\n"
                "zero product mention. Just answer the question well.\n"
            )

        user = (
            f"REDDIT POST:\n"
            f"r/{subreddit}\n"
            f"Title: {post_title}\n"
            f"Body: {post_body}\n"
            f"URL: {post_url}\n\n"
            f"Reply strategy: {product_angle or '(decide based on the thread)'}\n"
            f"Why this thread is relevant: {why_relevant or '(not provided)'}\n\n"
            "Draft the reply. Output ONLY the reply variants."
        )

        # First-pass: produce three angle variants in one call. The angles
        # we ask for differ based on whether a product mention is in play.
        if mention_product:
            variant_instructions = (
                "- Produce EXACTLY 3 distinct reply variants. Each takes a\n"
                "  different angle:\n"
                "    A) helpful answer with NO product mention\n"
                "    B) helpful answer with ONE subtle, in-line product mention\n"
                "    C) helpful answer led by shared founder experience, mention\n"
                "       the product as a personal aside\n"
            )
        else:
            variant_instructions = (
                "- Produce EXACTLY 3 distinct reply variants — NONE may mention\n"
                "  the product. Vary the angle instead:\n"
                "    A) concise, direct answer\n"
                "    B) longer answer with a relatable anecdote\n"
                "    C) answer that reframes the asker's problem\n"
            )
        variants_system = (
            system
            + "\n\nOUTPUT FORMAT (non-negotiable):\n"
            + variant_instructions
            + "- Separate variants with this exact line on its own, nothing else on\n"
            "  that line:\n\n  ---VARIANT---\n\n"
            "- Do not number or label them. Start directly with the first reply."
        )
        first_pass_raw = await llm.complete(
            [Message(role="system", content=variants_system), Message(role="user", content=user)],
            temperature=0.9,
            max_tokens=2400,
        )
        raw_chunks = [c.strip() for c in first_pass_raw.split("---VARIANT---") if c.strip()]
        if not raw_chunks:
            raw_chunks = [first_pass_raw.strip()]

        # Humanize + scrub each variant individually (cheap — short text).
        humanized_variants: list[str] = []
        for chunk in raw_chunks[:3]:
            cleaned_first = strip_draft_preamble(strip_reasoning(chunk)).strip().strip('"').strip("'")
            humanized = await llm.complete(
                [
                    Message(role="system", content=HUMANIZE_RULES),
                    Message(role="user", content=cleaned_first),
                ],
                temperature=0.5,
                max_tokens=900,
            )
            humanized_variants.append(
                _scrub(strip_draft_preamble(strip_reasoning(humanized)).strip().strip('"').strip("'"))
            )
        while len(humanized_variants) < 3:
            humanized_variants.append(humanized_variants[-1])

        action_id = store.create_action(
            project_id=project_id,
            run_id=run_id,
            action_type="reddit_reply",
            title=f"r/{subreddit}: {post_title[:80]}",
            content=humanized_variants[0],
            context={
                "subreddit": subreddit,
                "post_url": post_url,
                "post_title": post_title,
                "product_angle": product_angle,
                "why_relevant": why_relevant,
                "mention_product": mention_product,
                "variants": humanized_variants,
                "chosen_variant": 0,
            },
        )
        return json.dumps(
            {
                "ok": True,
                "action_id": action_id,
                "draft_preview": humanized_variants[0][:300],
                "variants": len(humanized_variants),
            }
        )

    @tool
    async def log_reddit_opportunity(
        post_url: str,
        subreddit: str,
        title: str,
        why_relevant: str,
        suggested_angle: str,
    ) -> str:
        """Record a Reddit thread as a copy-paste opportunity without drafting a full reply.

        Use when the thread is relevant but needs the user's personal voice or
        nuance — you flag it; they read and reply themselves.

        Args:
            post_url: Reddit thread URL.
            subreddit: Subreddit name (without r/).
            title: Post title.
            why_relevant: One sentence on why it matches the product.
            suggested_angle: How they should approach a reply (not a draft).
        """
        action_id = store.create_action(
            project_id=project_id,
            run_id=run_id,
            action_type="reddit_opportunity",
            title=f"r/{subreddit}: {title[:80]}",
            content=(
                f"**Why relevant:** {why_relevant}\n\n"
                f"**Suggested angle:** {suggested_angle}\n\n"
                f"**Link:** {post_url}"
            ),
            context={
                "subreddit": subreddit,
                "post_url": post_url,
                "why": why_relevant,
                "angle": suggested_angle,
            },
        )
        return json.dumps({"ok": True, "action_id": action_id})

    return [find_reddit_opportunities, draft_reddit_reply, log_reddit_opportunity]


_AI_TELLS = [
    (r"—", ", "),
    (r"–", "-"),                         # en-dash → hyphen
    (r"\bI'd love to\b", "I'd like to"),
    (r"\bI would love to\b", "I'd like to"),
    (r"\bhappy to help\b", ""),
    (r"\bhope this helps\b", ""),
    (r"\bhope that helps\b", ""),
    (r"\bfeel free to\b", ""),
    (r"\blet me know if you have any questions\b", ""),
    (r"\blet me know how it goes\b", ""),
    (r"\bbest of luck\b", "good luck"),
    (r"\bgreat question\b", ""),
    (r"\binteresting point\b", ""),
    (r"\bdelve into\b", "look at"),
    (r"\bdelve\b", "look"),
    (r"\bnavigate\b", "handle"),
    (r"\btapestry\b", "mix"),
    (r"\bin this digital age\b", ""),
    (r"\bin today's (fast-paced |digital |modern )?world\b", ""),
    (r"\bin the realm of\b", "in"),
    (r"\bit's important to note that\b", ""),
    (r"\bit's worth noting that\b", ""),
    (r"\bleverage\b", "use"),
    (r"\bleveraging\b", "using"),
    (r"\bsynergy\b", "fit"),
    (r"\brobust\b", "solid"),
    (r"\bseamless\b", "smooth"),
    (r"\bseamlessly\b", "smoothly"),
    (r"\bempower\b", "let"),
    (r"\bempowers\b", "lets"),
    (r"\bcomprehensive solution\b", "tool"),
    (r"\bunlock\b", "open"),
    (r"\bsupercharge\b", "speed up"),
    (r"\bgame[- ]changer\b", "big deal"),
    (r"\brevolutionize\b", "change"),
    (r"\bcutting[- ]edge\b", "current"),
]

# emoji ranges (broad coverage: misc symbols, emoticons, transport, supplemental)
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F6FF"     # misc symbols & pictographs, transport
    "\U0001F900-\U0001F9FF"     # supplemental symbols & pictographs
    "\U0001FA00-\U0001FAFF"     # symbols & pictographs extended-A
    "\U00002600-\U000027BF"     # misc symbols, dingbats
    "\U0001F1E6-\U0001F1FF"     # regional indicators (flags)
    "‍"                    # zero-width joiner (emoji sequence glue)
    "️"                    # variation selector (emoji presentation)
    "]+",
    flags=re.UNICODE,
)


def _scrub(text: str) -> str:
    out = text
    # phrase-level substitutions
    for pat, repl in _AI_TELLS:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    # strip emojis entirely
    out = _EMOJI_RE.sub("", out)
    # collapse spaces left behind by phrase removals
    out = re.sub(r" {2,}", " ", out)
    out = re.sub(r"\s+([.,!?])", r"\1", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    # remove empty parens/brackets left after emoji removal
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\[\s*\]", "", out)
    return out.strip()
