# Pulse — User Guide

A daily AI marketing operator that watches your product and hands you a copy-paste-ready action list every morning. This guide walks through everything Pulse can do today.

---

## 1. Setup

### Requirements

- macOS or Linux
- Python 3.12+
- Node.js 20+
- An [OpenAdapter](https://openadapter.dev) API key (any OpenAI-compatible key works — OpenAdapter is the cheapest path because Pulse runs on open-source models)

### Install

```bash
git clone <your-repo> pulse.cc
cd pulse.cc

# backend
uv sync                            # installs Python deps
cp .env.example .env
# put OPENADAPTER_API_KEY in .env
# (optional) PAGESPEED_API_KEY for higher Lighthouse quota

# frontend
cd web && npm install && cd ..
```

### Run

```bash
# terminal 1: backend
uv run pulse
# → http://127.0.0.1:8787

# terminal 2: frontend
cd web && npm run dev
# → http://localhost:3030
```

Open the frontend and the onboarding card greets you.

---

## 2. Adding your first project

Pulse only needs one input: **your product's URL**.

1. Type `acme.com` (or whatever your site is) in the URL field.
2. Hit **Start first dive**.
3. The dashboard loads immediately. Every panel begins with a **skeleton-loading state** while the agent works in the background.

### What the agent does during the first dive

In order, the agent:

1. **Crawls your site** (homepage + pricing + about + blog index). Fills in your project name, description, and competitor list.
2. **Extracts brand voice** from your existing copy (tone, vocabulary signatures, taboo words).
3. **Audits on-page SEO** (meta tags, h1 structure, OG tags, alt text, robots, sitemap, structured data). Each finding becomes an action.
4. **Analyzes competitors** with web search + scrape. Surfaces 2–3 closest alternatives.
5. **Identifies positioning gaps** vs the competitors you might exploit.
6. **Scans Hacker News** (via the public Algolia API) for threads where your product is relevant. Each becomes a copy-paste opportunity.
7. **Scans Reddit** (public JSON API) for threads where your product is relevant. Drafts a reply or logs the thread, depending on fit.
8. **Drafts content**: one tweet introducing the product, one 800-word blog article on a top-of-funnel topic.
9. **Generates a 30-day marketing strategy** in markdown.

You can watch this happen live in the **terminal bar** at the top of the dashboard. It humanizes each tool call into a readable line ("Crawling acme.com…", "Auditing SEO…", "Drafting tweet…").

A first dive takes 2–4 minutes typically. You don't have to wait — panels fill in progressively.

---

## 3. The dashboard

Pulse uses a 4-column layout on desktop:

```
┌──────────┬─────────────┬────────────────┬───────────────┐
│ Company  │ Analytics   │ Actions Feed   │ Talk to Pulse │
└──────────┴─────────────┴────────────────┴───────────────┘
```

On tablet (md), the Company sidebar collapses (use the project switcher to see other projects). On mobile, you swap between the four panes with the bottom nav.

### Column 1 — Company sidebar

Everything Pulse knows about your product.

- **Name + URL**: the product identity.
- **Description**: a 1–3 sentence summary. Click to edit inline.
- **Documents**: jump-links to Product Information, Competitor Analysis, Brand Voice, Marketing Strategy, Articles. A green **New** badge means there's pending material to read.
- **Competitors**: chip list. Click `+ add` to add your own; hover any chip to remove.
- **Voice**: the extracted tone and vocabulary signatures Pulse will mimic when drafting.
- **Schedule**: the time of day daily runs fire (default 06:00 UTC, editable per project).

### Column 2 — Site Analytics

Five tabs:

- **Health** *(default)* — on-page SEO score (0-100), severity breakdown (high/medium/low), and **PageSpeed gauges** (Performance / Accessibility / Best-practices / SEO, both mobile and desktop) once `check_pagespeed` has run. Also shows Core Web Vitals (LCP, FCP, CLS, TBT) and top opportunities from Lighthouse.
- **Traction** — your **digital footprint**. Hit *Scan footprint* and Pulse searches the web, Reddit, and Hacker News for your product name + URL, classifies every mention by platform, and shows where you're strong, the sentiment, and a "where to focus" list. See §11.
- **Technical** — signal list (sitemap, JSON-LD, HSTS, etc.) and findings with severity.
- **AI / GEO** — coming soon (how ChatGPT / Claude / Perplexity cite your site).
- **Checks** — every check that passes, grouped by category.

When data hasn't loaded yet, panels show shimmer skeletons. When the first dive completes, real data swaps in.

### Column 3 — Actions Feed

Everything Pulse has prepared for you to ship. Grouped into collapsible categories:

| Category         | What it contains                                              |
|------------------|---------------------------------------------------------------|
| **SEO & GEO**    | High/medium/low-severity SEO fixes with step-by-step guides   |
| **X Writer**     | Tweet drafts in your brand voice                              |
| **Reddit**       | Drafted replies + flagged opportunities by subreddit          |
| **Articles**     | Long-form drafts in markdown                                  |
| **Hacker News**  | Flagged threads worth replying to                             |
| **LinkedIn**     | Post drafts                                                   |
| **Positioning**  | Market-gap opportunities vs your competitors                  |
| **Strategy**     | 30/60/90-day marketing plans                                  |

Filter by status: **Pending / Shipped / Dismissed / All**. Click any action to open its detail sheet.

Each action group header also has a **+** button to **generate one more of that
kind on demand** (a tweet, a Reddit reply, an article, an SEO audit…) without
waiting for the next daily run. Type an optional topic and hit Generate.

### Column 4 — Talk to Pulse

A chat with the agent. Same tool registry as scheduled runs, so you can say:

- *"draft a tweet on X"*
- *"audit my homepage SEO"*
- *"what should I post on LinkedIn this week?"*
- *"find me an article topic that ranks for AI gateway"*
- *"are there any new HN threads worth replying to?"*

The agent uses tools live and saves drafts straight to the Actions Feed.

**Multi-session chat**: every new conversation is its own session. Click the message-square icon to see history. Sessions auto-title from your first message. Delete any session from the history view.

---

## 4. Working with actions

### Opening an action

Click any row in the Actions Feed. A **detail sheet** slides in from the right.

For most actions you'll see:

- **Channel pill** (SEO, Reddit, X, etc.)
- **Title + metadata** (severity, age, source URL where applicable)
- **A/B/C variants** — content drafts (tweets, Reddit replies, LinkedIn, HN, articles) come as three distinct variants. Tab between A / B / C; the one you pick becomes the saved content.
- **Draft card** with the full content
  - **Copy** button — one-click clipboard
  - **Copy & open post** (Reddit/HN) — copies the chosen variant and opens the platform's compose page
  - **Edit** button — inline editor for title + body, saves to the database
  - **Mark Complete** — moves it to Shipped
- **Why this thread** callout (Reddit/HN) — the relevance reason + suggested angle the agent derived, shown above the draft.
- **Step-by-step guide** (SEO fixes + positioning gaps) — the agent generates a detailed remediation guide on demand. First open triggers generation; subsequent opens are instant from cache.

### Copy-paste, not auto-post

Pulse never posts on your behalf. Every action is a draft you copy and paste from your own account. This:

- Avoids platform bans for automated content.
- Keeps you in the loop on what's being shared.
- Lets you tweak the voice before it goes out.

### Reddit drafts specifically

Reddit replies go through a two-pass LLM process:

1. **First pass** drafts the reply following anti-spam rules (5+ sentences of value before any product mention; match subreddit tone; avoid AI tells).
2. **Humanize pass** scrubs em-dashes, "I'd love to", "happy to help", "delve into" and similar AI tells.

Even with that, *read the draft before posting*. Reddit anti-spam moderation can be brutal — context matters.

---

## 5. Multiple projects

Click the project pill in the header (next to the `pulse` logo) to open the **project switcher**:

- See every project with a live status dot (spinning loader = run in progress).
- Switch projects with one click.
- Hit **Add new project** to drop a fresh URL.

`⌘N` / `Ctrl+N` opens the Add Project modal from anywhere.

Each project has its own:

- Analytics, actions, runs, chat sessions
- Brand voice
- Writing instructions (per-channel rules)
- Schedule (when its daily run fires)

---

## 6. Customizing what Pulse writes

Click the **sliders icon** in the Actions Feed header — or the **settings icon** in the top-right — to open **Writing Instructions**.

Per-channel customization:

- **Daily SEO fixes toggle** — guarantee at least one SEO recommendation per daily run.
- **Hacker News** — extra prompt instructions + search keywords (capped at 10).
- **X** — extra prompt instructions ("prioritize contrarian hooks…").
- **LinkedIn** — extra prompt instructions ("founder voice, short paragraphs…").
- **Reddit** — extra prompt instructions + **priority subreddits** (up to 5, chip input) + **keywords** (up to 10) + **region**.

These instructions are stitched into the system prompt for each draft. They take effect immediately — the next run / chat draft uses the new rules.

---

## 7. Daily runs

Pulse runs once per day per project, in the background. Default 06:00 UTC.

- New actions land in the Actions Feed.
- A daily run aims for 3–5 actions total — quality > quantity.
- Different angles than recent runs (the prompt explicitly biases away from repetition).

**Run now** in the header triggers a daily run on demand. **First dive** is only on a brand-new project; subsequent manual runs are daily-shaped.

`g` from anywhere (outside a text field) triggers a run. The **Run now** button
is a split-button — the caret menu also has **Redo first dive** (a full re-scan).

### Schedule + versions

Set **when and how often** the daily pass fires in the project settings sheet
(**Run schedule**): once a day, twice a day, or a custom list of times.

Every completed first-dive / daily run snapshots a **version** — open the
**history icon** in the header to see the timeline. Each version carries a short
"what changed since last time" summary plus delta chips (new actions, SEO
movement, traction change, run cost). It's a running changelog of your growth.

---

## 8. Launch mode

Click **Launch** in the header to open the launch workspace — an archetype-driven
go-to-market plan for a *new* product launch (distinct from ongoing daily ops).

1. **Auto-classify** — Pulse reads everything it already knows (the crawl + the
   Product Information doc) to infer pricing, audience, primary artifact,
   retention loop, and OG-unfurl, then classifies the product into one of six
   growth archetypes (viral-artifact, dev-tool, B2B SaaS, consumer, open-source,
   marketplace). You confirm or override — no form to fill.
2. **Week-1 plan** — the archetype fixes the channel sequence, north-star metric,
   and anti-patterns; the model customizes positioning + a day-by-day board
   (Day 0 pre-launch gate through Day 7). Each day has a goal, a rationale, tasks,
   and the **actual posts to write** that day.
3. **Generate content inline** — every content piece has a *Write it* button that
   produces three humanized, platform-specific variants right in the card, with a
   *Copy & open* button to the platform's compose page. Drafts also land in your
   Actions feed.
4. **Track** — a live tracker (mirrors a launch spreadsheet, server-synced): fill
   in each day's numbers and the summary strip computes K-factor, funnel %, and
   task completion. Hit **get move** for the single most important next action,
   derived from the archetype's decision rules.

---

## 9. Settings → Providers

Click your profile (top-right) → **Providers** to manage LLM providers without
touching `config.yaml`:

- Add / edit / remove any OpenAI-compatible provider (base URL, API key).
- **Fetch models** pulls the provider's model list; **Test connection** verifies it.
- Set each provider's **role** — primary, secondary (failover), vision, or fallback.
- Set per-token pricing for cost tracking.

Runtime edits persist to `~/.pulse/settings.json` and override the YAML. Your
last run's cost + token count show in the profile pill.

---

## 10. Keyboard shortcuts

| Shortcut    | Action                                |
|-------------|---------------------------------------|
| `⌘K` / `Ctrl+K` | Open chat (on mobile, switches pane) |
| `⌘N` / `Ctrl+N` | New project                       |
| `g`         | Run now (when not in a text field)    |
| `Esc`       | Close detail sheet / modal            |
| `↵` in chat | Send message                          |
| `⇧↵` in chat | Newline                              |

---

## 11. Traction (digital footprint)

The **Traction** tab (Site Analytics → Traction) maps where your company is
talked about across the internet.

Hit **Scan footprint** and Pulse:

1. Derives search terms from your product name and URL (together and separate).
2. Fans out parallel searches across the open web, Reddit, and Hacker News.
3. Classifies every mention by platform (Reddit / HN / X / GitHub / Product Hunt /
   LinkedIn / blogs / directories / web), dropping your own domain.
4. Runs one synthesis pass that scores each platform's **strength**
   (strong / emerging / thin / none), assesses sentiment, and produces 3-5
   concrete **"where to focus"** insights.

The result is your digital fingerprint: summary tiles (strongest platform, total
mentions, sentiment), the insights, and one expandable card per platform listing
the actual mentions (title, snippet, link, date, score). Rescan anytime.

This is the "where are we already strong, where should we lean in" view — e.g.
"you're strongest on Reddit in r/LocalLLaMA, double down there; no Hacker News
presence yet, a Show HN could open a new audience."

---

## 12. Status pill + terminal

The top-left has two pills:

- **Project pill** — the current site, with a status dot (spinning = running).
- **Status pill** — `STANDBY` (no first dive), `RUNNING` (active), `IDLE` (done).

Below the header is the **terminal bar**. Collapsed by default, click to expand. While a run is in flight, every tool call lands as a line:

```
> Crawling acme.com…
✓ 9 pages fetched
> Auditing SEO on acme.com…
✓ SEO score: 84/100 · 0 high, 2 medium
> Searching: acme alternatives 2026
…
```

This is the audit trail — what the agent did, what it found.

---

## 13. Data + privacy

Everything stays on your machine:

- Project data, actions, run logs → SQLite at `~/.pulse/pulse.db`.
- Chat sessions → same SQLite.
- The agent talks to OpenAdapter for LLM + web search. No other third-party calls except:
  - Google PageSpeed Insights (optional, for Lighthouse scores)
  - Hacker News Algolia API (public, no auth)
  - Reddit JSON API (public, no auth)

Wipe everything with `rm ~/.pulse/pulse.db`.

---

## 14. Models & cost

Pulse routes every LLM call through OpenAdapter. The default chain is:

1. **MiniMax-M2.5** (primary — token-streams cleanly with tools)
2. **0G-GLM-5.1** (fallback)
3. **0G-GLM-5** (fallback)

A full first dive costs roughly **$0.05–0.20** in tokens at OpenAdapter pricing, vs $1–5 for the equivalent on GPT-4o. A daily run is even cheaper.

You can swap providers in `config.yaml` under `llm.providers` — any OpenAI-compatible endpoint works.

---

## 15. Troubleshooting

**Onboarding says "backend unreachable"**
Backend isn't running. Run `uv run pulse` from the repo root.

**Skeletons never resolve**
The first dive may have failed. Check the terminal bar for an `error` line, or run `curl http://127.0.0.1:8787/projects/1/runs` to see run status.

**Reddit / HN returns nothing**
The agent's keyword list may not match your product. Add keywords in **Writing Instructions → Hacker News / Reddit → Search keywords**.

**PageSpeed doesn't fill in**
PageSpeed Insights has a low free quota without a key. Add `PAGESPEED_API_KEY` to `.env` and re-run.

**An action looks generic**
Open it, hit **Edit**, fix the draft, save. Then update **Brand Voice** in the company sidebar (or ask the chat agent to re-extract). Future drafts use the corrected voice.

**Daily runs aren't firing**
Check the scheduler. By default it's enabled in `config.yaml` (`scheduler.enabled: true`, hour 6, minute 0 UTC). The cron fires only while the server is running.

---

## 16. Tool inventory

What's available to the agent today (21 tools):

**Discovery & analysis**
`crawl_website`, `analyze_competitor`, `audit_seo`, `check_pagespeed`, `web_search`, `news_search`, `read_url`, `find_hn_opportunities`, `find_reddit_opportunities`

**Content drafting**
`draft_tweet`, `draft_hn_post`, `draft_linkedin_post`, `draft_article`, `draft_reddit_reply`

**Opportunity logging**
`log_seo_fix`, `log_hn_opportunity`, `log_reddit_opportunity`

**Strategy**
`extract_brand_voice`, `update_project_info`, `generate_marketing_strategy`, `identify_market_gaps`

---

## 17. Not yet built

- Auto-posting (intentional — copy-paste only)
- Google Analytics / Search Console / PostHog integration (live launch-tracker numbers are entered manually for now)
- Twitter mention search (paid API, deferred)
- Multi-tenant teams + auth
- Browser extension for one-click posting

---

## 18. Where to look in the code

- Backend agent loop → [src/pulse/agent.py](src/pulse/agent.py)
- Tool registry + each tool → [src/pulse/tools/](src/pulse/tools/)
- First-dive + daily + targeted prompts → [src/pulse/orchestrator.py](src/pulse/orchestrator.py)
- Launch mode (archetypes, plan, content) → [src/pulse/launch.py](src/pulse/launch.py)
- Traction scan → [src/pulse/traction.py](src/pulse/traction.py)
- HTTP API → [src/pulse/server.py](src/pulse/server.py)
- Frontend dashboard glue → [web/src/app/page.tsx](web/src/app/page.tsx)
- Per-panel components → [web/src/components/](web/src/components/)

Happy shipping.
