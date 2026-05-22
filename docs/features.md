# Pulse — Features

A detailed tour of everything Pulse does. For a hands-on walkthrough see the
[User Guide](USER_GUIDE.md); for how it's built see [Architecture](architecture.md).

---

## Projects

A **project** is one product Pulse manages. You add it with a single input —
the URL. From that, the first dive infers the name, description, competitors,
and brand voice. You can run several projects; each has its own actions,
analytics, schedule, brand voice, writing instructions, launch campaign, and
version history. Switch with the project pill in the header (`⌘N` to add one).

---

## Runs

Pulse works in **runs** — bounded agent loops that produce actions. Four kinds:

| Kind | Trigger | Shape |
|---|---|---|
| **first_dive** | new project / "Redo first dive" | the big initial scan — crawl, brand voice, SEO/GEO/links audit, product doc, starter content, HN/Reddit scan, 30-day strategy |
| **daily** | scheduler or "Run now" | 3-5 fresh, shippable actions; biased away from repeating recent angles |
| **targeted** | a channel "+" button | one artifact of a chosen kind, fast (4-8 iterations) |
| **manual** | chat | ad-hoc instruction handled by the chat agent |

You watch any run live in the console (SSE token stream + humanized tool calls).

### First dive (what the agent does, in order)

1. `crawl_website` — homepage + pricing + about + blog → name, description, competitors
2. `extract_brand_voice` — tone, vocabulary signatures, taboo words
3. `generate_product_information` — the Product Information document
4. `audit_seo`, then `audit_geo` + `audit_links` on the homepage → logged fixes
5. starter content: a tweet + a news-grounded article
6. `generate_marketing_strategy` (30-day)
7. `find_hn_opportunities` → log the best threads
8. `find_reddit_opportunities` (the smart pipeline) → draft a reply + log one
9. (if iterations remain) competitor analysis + market gaps

---

## Founder-voice drafting

Every content draft is written to sound like a real founder shipping, not a
content marketer. The voice rules are enforced in the prompts **and** scrubbed
post-hoc: no em-dashes, no emojis, no hashtag spam, no marketing words
(leverage / robust / synergy / seamless / unlock / supercharge…), no
AI-assistant tells ("I'd love to", "happy to help", "delve into"). Lowercase
opens, contractions, specific numbers over adjectives.

Channels: **tweets, LinkedIn posts, Show HN posts, blog articles, Reddit
replies**. Each draft is produced as **3 A/B/C variants** taking different
angles; you tab between them and the one you pick becomes the saved content.

Articles can be **news-grounded**: the agent runs `news_search`/`web_search`
first and weaves recent, dated, attributed findings into the piece.

---

## Smart Reddit discovery

Finding the right Reddit threads is a 6-stage pipeline, not a keyword search:

1. **Profile** — the LLM turns the product into pain points, audience, use cases
2. **Query plan** — generates 18-24 queries grouped by intent (pain, switching,
   shopping, comparison, question) — e.g. "alternative to X", "tired of Y"
3. **Search** — fans out across `old.reddit.com` / `api.reddit.com`, filters out
   deleted/locked/NSFW/self-promo and your own product
4. **Regex score** — weighted intent patterns (switching intent 40, frustration
   35, shopping 30…) + recency
5. **LLM verify** — a batched call scores each candidate 0-100 on *real* semantic
   relevance, recommends a reply angle, and decides whether to mention the product
6. **Rank** — `final = regex*0.35 + llm*0.65`; top 10 returned with
   `suggested_angle` + `mention_product`, which feed `draft_reddit_reply`

Reddit (and HN) replies are read-only — drafts you copy-paste; Pulse never posts.

---

## Site audits (Analytics panel)

Six tabs:

- **Health** — on-page SEO score + findings, PageSpeed gauges (perf / a11y /
  best-practices / SEO, mobile + desktop), Core Web Vitals, top opportunities.
- **Traction** — see below.
- **Links** — internal vs external link counts on the homepage + a HEAD-check
  that flags broken links.
- **AI / GEO** — generative-engine optimization: can ChatGPT (GPTBot), Claude
  (ClaudeBot), Perplexity (PerplexityBot), and Gemini (Google-Extended) crawl
  you? Plus llms.txt, JSON-LD + FAQ schema, question-style headings, and meta
  description. Scored, with per-engine readiness and concrete fixes.
- **Technical** — site signals (sitemap, JSON-LD, HSTS…) and findings.
- **Checks** — everything that passes, grouped by category.

Health/SEO populates during the first dive; Links and AI/GEO run during the
dive and can be re-run on demand from their tab.

---

## Traction (digital footprint)

Maps where the company is talked about across the internet. *Scan footprint*:

1. derives search terms from the product name + URL
2. fans out across the open web, Reddit, and Hacker News
3. classifies every mention by platform (Reddit / HN / X / GitHub / Product Hunt
   / LinkedIn / blogs / directories / web), dropping your own domain
4. one LLM pass scores each platform's strength (strong / emerging / thin /
   none), sentiment, and 3-5 "where to focus" insights

You get summary tiles (strongest platform, total mentions, sentiment), the
insights, and one expandable card per platform with the actual mentions.

---

## Launch mode

An archetype-driven go-to-market workflow for a *new* launch (distinct from
daily ops). Opened from the **Launch** button.

1. **Classify** — auto-infers intake (pricing, audience, artifact, retention
   loop, OG-unfurl) from the crawl + Product Information doc, then maps the
   product to one of six growth archetypes: viral-artifact, dev-tool, B2B SaaS,
   consumer, open-source, marketplace. You confirm or override.
2. **Plan** — the archetype fixes the channel sequence, north-star metric, and
   anti-patterns; the model customizes positioning + a day-by-day Week-1 board.
   Each day has a goal, rationale, tasks, and the actual posts to write.
3. **Generate** — every content piece has a *Write it* button producing three
   humanized, platform-specific variants inline, with a *Copy & open* shortcut
   to the platform's compose page.
4. **Track** — a live tracker (server-synced): fill in each day's numbers and
   the summary strip computes K-factor, funnel %, and task completion. *Get move*
   applies the archetype's decision rules to surface the single most important
   next action.

The archetype table (growth engine, north-star, channels, anti-patterns) is the
core IP — encoded as data, not prose, so the output is non-generic.

---

## Per-channel generation

Every action group header has a **+** button to generate one more of that kind
on demand — a tweet, a Reddit reply, an article, an SEO audit — without waiting
for the next daily run. Optional topic, then Generate.

---

## Scheduling

Set when and how often the daily pass fires (project settings → Run schedule):
**once**, **twice**, or a **custom** list of times. Each time registers its own
cron job. The scheduler runs while the server is up.

---

## Versioning

Every completed first-dive / daily run snapshots a **version**: action counts by
type, new-this-run, SEO score, traction mentions, run cost/tokens/iterations.
An LLM writes a short *"what changed since last time"* note comparing to the
previous snapshot. Open the history icon in the header for a timeline with delta
chips (new actions, SEO ±, ±mentions, cost) — a running changelog of your growth.

---

## Usage ledger

Every LLM operation is metered into a ledger — main runs, per-channel content
generation, competitor analysis, traction scans, launch infer/classify/plan/
draft, chat, action expansion. The profile menu shows **Last run** and
**Overall** (all-time) token + cost totals.

---

## Providers & cost

Configure any OpenAI-compatible providers in `config.yaml` or live from
**Settings → Providers** (base URL, key, fetch models, set primary/secondary/
vision roles, test connection, per-token pricing). Calls fail over in role
order. Runtime edits persist to `~/.pulse/settings.json` and override the YAML.

Pulse defaults to [OpenAdapter](https://openadapter.dev) (cheap open-source
models) but works with OpenAI, OpenRouter, Together, Groq, or a local Ollama/
vLLM server.

---

## Chat

A full chat with the agent (per-project, multi-session) sharing the same tool
registry as scheduled runs. Ask it to draft, audit, find threads, or answer
strategy questions; drafts land in the Actions feed. Sessions auto-title and
persist.
