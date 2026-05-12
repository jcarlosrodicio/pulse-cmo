# AI Growth Agent — Spec

> Autonomous marketing agent for indie products. Runs daily, identifies opportunities, drafts content, you copy-paste to ship. Inspired by Okara's AI CMO but cheaper, open, and built on OpenAdapter.

> Status: **next-week project**, not overnight. This spec is for the multi-week build after stackd.cc ships.

---

## 1. Vision

**Pitch:** A personal CMO that wakes up every morning, audits your site, scans Reddit/HN/Twitter for opportunities, drafts replies and posts in your voice, and hands you a daily action list. You spend 10 minutes a day copy-pasting; the agent does the rest.

**Why now:**
- Indie devs are drowning in marketing tasks they don't know how to do.
- AI agents with tool use are good enough to handle the boring parts (SEO audits, finding mentions, drafting replies).
- LLM costs have dropped 100x with open-source models via OpenAdapter — what Okara needs $99/mo to cover, you can do for $19.

**North-star metric:** number of agent-suggested actions shipped per user per week. If it's < 3, the agent isn't useful.

---

## 2. The OpenAdapter wedge (most important section)

This is **the** differentiator. Read it twice.

Okara at $99/mo is probably burning $20-40 of that on GPT-4 tokens. A "deep dive" with web search, competitor analysis, content drafting, and Reddit scanning is easily 50-200 LLM calls. At GPT-4 prices, that's $1-5 per run.

Your agent uses OpenAdapter's base URL + API key. Behind that you route to:
- DeepSeek V3 / R1 for reasoning ($0.27/M tokens vs GPT-4o's $5/M)
- Qwen 2.5 Coder for code/technical analysis
- Kimi K2 for long-context (full-site analysis)
- GLM-4.5 for content drafting in voice

**Effective cost per daily run: ~$0.05-0.20.** Sustainable at $19/mo. Underprice Okara by 80% while dogfooding your own product.

**Marketing angle — write this on the landing page literally:**
> "AI CMO without the $99/month bill. We run on open-source models through OpenAdapter, so we charge what it actually costs."

This also makes the AI Growth Agent the flagship demo for OpenAdapter. Cross-promotion is built in: every CMO product page has "powered by OpenAdapter" and every OpenAdapter case study features this product. Two-product flywheel.

---

## 3. Competitive landscape

**Direct competitor: Okara (askokara.com)**
- Pricing: $99/mo
- Strengths: polished UI, established
- Weaknesses: expensive (GPT-4 cost pass-through), generic content, limited customization
- They proved the market — there's demand

**Adjacent competitors:**
- **Ahrefs / Surfer SEO** — SEO-focused, not agent-driven, expensive ($99-$399/mo)
- **Gigabrain** — Reddit-only research, no content drafting
- **Frase / MarketMuse** — content briefs, not agentic
- **Athena (athenahq.ai)** — marketing AI for B2B, enterprise pricing
- **Generic ChatGPT/Claude** — people DIY this for free, but lose continuity and don't have integrations

**Your positioning:**
> "The indie founder's CMO. Cheaper than Okara, broader than Ahrefs, more useful than a ChatGPT tab."

Target audience: solo founders and indie hackers with one product, no marketing budget, no time. Devs who can integrate things themselves. Not enterprise.

---

## 4. Core User Flows

### Flow A — First-time setup (the magic moment)
1. User signs up, enters their site URL.
2. Agent runs the "first dive" — visible terminal-style log:
   ```
   > Crawling [site]...
   > Reading product info...
   > Analyzing positioning...
   > Identifying competitors...
   > Searching: [their product] alternatives 2026
   > Building competitor matrix...
   > Auditing SEO...
   > Found 7 opportunities
   > Generating brand voice profile...
   > Drafting initial marketing strategy...
   > Done. Your AI CMO is ready.
   ```
3. Dashboard fills in live: Company panel (extracted info), Analytics panel (SEO scores, PageSpeed), Actions feed (opportunities ready to action).
4. User can edit anything the agent inferred (product description, brand voice, competitors).

### Flow B — Daily run (the recurring habit)
1. Agent auto-runs at user's chosen time (default 6 AM their TZ).
2. Generates a daily action list: ~2 SEO fixes, ~1 article topic, ~2 Reddit replies, ~1 tweet, ~1 LinkedIn post, ~1 HN comment opportunity.
3. User gets email/push notification: "Your CMO is ready — 5 minutes to ship today's actions."
4. User opens dashboard, reviews each item, copies content, posts to the relevant platform.
5. Optional: agent tracks which actions were taken (via webhook from PostHog or manual "mark as done").

### Flow C — Ask the CMO (always-on chat)
- Right rail: "Talk to AI CMO" chat
- Agent has full context: site info, brand voice, history of suggestions, analytics data
- Use cases: "draft a launch tweet," "should I start a substack?", "what's my best content angle this week?"

---

## 5. Agent Architecture

This is the heart of the product. Keep it simple and effective.

### Architecture pattern: **ReAct loop with tool calling**

```
┌──────────────────────────────────────────────────┐
│  Trigger (manual / cron / chat message)          │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│  Agent Orchestrator (FastAPI background task)    │
│                                                  │
│  while not done:                                 │
│    thought = llm.plan(state, available_tools)    │
│    tool_calls = llm.choose_tools(thought)        │
│    results = execute_tools_parallel(tool_calls)  │
│    state.update(results)                         │
│    stream_log_to_frontend(thought, results)      │
│                                                  │
│  return final_actions[]                          │
└────────────────────┬─────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────┐
│  Persist actions → Postgres                      │
│  Stream final state → frontend via SSE/WS        │
└──────────────────────────────────────────────────┘
```

### LLM routing strategy (via OpenAdapter)

Different model for different tool, picked by the orchestrator based on task type:

| Task | Model (via OpenAdapter) | Why |
|---|---|---|
| Orchestration / planning | DeepSeek V3 | Best reasoning per dollar |
| Content drafting (tweet/article) | GLM-4.5 or Claude Haiku | Voice matching, creativity |
| Long-context site analysis | Kimi K2 (200k+ context) | Whole-site at once |
| Code/technical SEO analysis | Qwen 2.5 Coder | Structured output reliable |
| Quick classification | DeepSeek Chat | Cheap, fast |

Single config table maps task → model, easily tunable per user later.

### Streaming the log

The terminal-style "Running Daily" log is the UX magic — it makes the agent feel alive. Implement as Server-Sent Events from the FastAPI backend. Every thought + tool call + result streams to the frontend in real time.

---

## 6. Tool Inventory (the functions)

Each is a clean Python function exposed to the LLM via function calling. Start with these for MVP:

### Core analysis tools
- `crawl_website(url, max_pages=20)` — fetches sitemap, reads main pages, extracts product info / pricing / blog / docs.
- `search_web(query, num_results=10)` — uses Tavily or Brave Search API; cheap and good.
- `audit_seo(url)` — runs Lighthouse via PageSpeed Insights API + custom checks (meta tags, alt text, schema markup, robots.txt, sitemap.xml).
- `check_pagespeed(url)` — Lighthouse scores for mobile + desktop.
- `analyze_competitor(competitor_url)` — crawl competitor, extract pricing/features/positioning.

### Integration tools
- `fetch_google_analytics(date_range)` — needs OAuth, reads sessions / top pages / sources.
- `fetch_search_console(date_range)` — needs OAuth, reads top queries / CTR / impressions.
- `fetch_posthog(date_range)` — needs API key, reads events / funnels.

### Discovery tools
- `find_reddit_opportunities(keywords[], subreddits[])` — searches Reddit for recent posts asking questions your product can answer. Returns post URL, title, body, suggested approach.
- `find_hn_opportunities(keywords[])` — same for HN — finds recent threads where your product is relevant.
- `find_twitter_mentions(keywords[])` — Twitter API search for product mentions + adjacent conversations.

### Content drafting tools
- `draft_reddit_reply(post_url, brand_voice, product_context)` — generates a helpful human-toned reply that mentions the product naturally without being spammy. Critical: trained to avoid "I built X" energy unless it fits.
- `draft_tweet(topic, brand_voice)` — single tweet or thread.
- `draft_hn_post(topic, angle)` — Show HN / Ask HN style.
- `draft_linkedin_post(topic, brand_voice)` — LinkedIn-flavored, slightly more formal.
- `draft_article(topic, target_keywords, length, brand_voice)` — full article in markdown.

### Strategy tools
- `update_brand_voice(samples[])` — analyzes user's writing samples → produces a voice profile (tone, vocabulary, sentence rhythm, taboo words).
- `generate_marketing_strategy(timeframe)` — outputs a 30/60/90 day plan from current state.
- `identify_market_gaps(competitors[])` — finds positioning gaps the user can exploit.

### Reddit replies — the killer feature, design notes:

Reddit anti-spam is brutal. Your drafted replies must:
- Lead with answering the actual question (5+ sentences of value before any product mention)
- Mention the product as "I built X for this" only if it actually fits — sometimes the right reply has no product mention at all
- Match the subreddit's tone (r/SideProject is forgiving, r/programming will downvote into oblivion)
- Be obviously human — vary length, use casual punctuation, occasional typos OK
- Never use em-dashes, "I'd love to", "happy to help", and similar AI tells

Have a separate model + prompt pass dedicated to "humanize this reply." Worth the extra LLM call.

---

## 7. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI (Python) | Async, great for agent tool calling, good ecosystem |
| LLM access | OpenAdapter (your own product) | The wedge. Cheap models, dogfooded. |
| Search | Tavily or Brave Search API | Cheap, good results, easy integration |
| Frontend | React + Vite + Tailwind | Fast iteration |
| Realtime | Server-Sent Events (FastAPI native) | Simpler than WebSockets for log streaming |
| DB | Postgres (Supabase) | Same as stackd, you'll know it well |
| Queue / background tasks | Celery + Redis, or FastAPI BackgroundTasks for MVP | Daily runs need scheduling |
| Auth | Supabase Auth → Clerk later | Same as stackd |
| Payments | Stripe Checkout | Standard |
| Crawling | Playwright + httpx | Playwright for JS-rendered sites |
| Lighthouse | PageSpeed Insights API | Free, no infra |
| Reddit | PRAW (Python Reddit API Wrapper) | Need to be careful with rate limits + read-only mode |
| Email | Resend or Postmark | Daily digest emails |

### Why not Next.js for everything?
Agent loops are long-running, server-heavy, Python-native (LangChain/LangGraph/Pydantic AI ecosystem). FastAPI is the right tool. React frontend talks to FastAPI via REST + SSE.

### Agent framework choice
**Recommendation: Pydantic AI** — typed tool definitions, clean async, lighter than LangChain.
Alternative: write the orchestration loop yourself in ~200 lines. For MVP this is fine and gives full control. Don't over-frameworkize early.

---

## 8. Data Model

```sql
users (
  id, email, name, handle, created_at,
  subscription_tier, stripe_customer_id
)

projects (  -- one user can have multiple products
  id, user_id,
  name, url, description, brand_voice (jsonb),
  competitors (text[]),
  schedule (cron expr, default '0 6 * * *' in user TZ),
  integrations (jsonb)  -- {ga: {token}, gsc: {token}, posthog: {key}}
)

agent_runs (
  id, project_id, started_at, finished_at, status,
  total_tokens, total_cost_usd,
  log (jsonb[])  -- streamed thoughts + tool calls + results
)

actions (
  id, project_id, run_id,
  type ('seo_fix' | 'reddit_reply' | 'tweet' | 'hn_post' | 'linkedin' | 'article'),
  title, content (text), context (jsonb),
  status ('pending' | 'shipped' | 'dismissed'),
  shipped_at, source_url
)

seo_findings (
  id, project_id, run_id,
  severity, category, description, fix_instructions
)

reddit_opportunities (
  id, project_id, run_id,
  post_url, subreddit, post_title, post_body, post_score, post_age_hours,
  suggested_reply, status, dismissed_reason
)

content_drafts (
  id, project_id, run_id, type, topic, body,
  status, shipped_at, performance_data (jsonb)
)
```

---

## 9. Integrations

### Tier 1 (MVP — must have)
- **Google PageSpeed Insights** — free API key, no OAuth. Get this working day 1.
- **OpenAdapter** — your own. Just env vars.
- **Tavily** or **Brave Search** — for `search_web` tool.
- **Reddit (read-only via PRAW)** — no OAuth needed for searching public posts. Posting requires user OAuth (not in MVP — copy-paste only).

### Tier 2 (week 2-3)
- **Google Analytics 4** — OAuth flow, painful but worth it.
- **Google Search Console** — OAuth, same flow as GA.
- **PostHog** — API key based, easier.

### Tier 3 (later)
- **Twitter API** — expensive ($100/mo for basic). Skip until paid users ask.
- **Hacker News** — public API, no auth. Easy.
- **LinkedIn** — no decent public API. Copy-paste only, forever.

### Critical decision: copy-paste vs auto-post
**Copy-paste only for MVP.** Auto-posting is:
- Risky (banned accounts, spam flags)
- High-support (people will blame the agent for bad outcomes)
- Legally murky on some platforms

Copy-paste keeps the user in the loop, builds trust, and you can always add auto-post for paid tiers later if users demand it.

---

## 10. Monetization

### Pricing
| Tier | Price | What you get |
|---|---|---|
| Free | $0 | 1 site, 1 first-dive run, view results read-only |
| Hobby | $19/mo | 1 site, daily runs, basic actions (SEO + content drafts), no integrations |
| Pro | $49/mo | 3 sites, all integrations, Reddit + HN opportunities, daily email digest |
| Studio | $99/mo | 10 sites, priority queue, custom brand voice training, API access |

Compare to Okara at $99/mo flat — you have a clear cheaper-tier story.

### Unit economics check
- Average daily run cost via OpenAdapter: ~$0.10-0.30
- Pro tier user at $49/mo with daily runs: ~$9/mo in LLM costs
- Gross margin: ~80%. Healthy.

### Free tier strategy
Free tier exists to let people see one impressive demo run. Don't give away daily runs for free — they're recurring cost. One run with great output → upgrade prompt.

---

## 11. MVP Scope (multi-week, not overnight)

### Week 1 — Core agent loop
- FastAPI backend skeleton
- OpenAdapter integration, test 3 models work
- Agent orchestrator with Pydantic AI
- Tools: `crawl_website`, `search_web`, `audit_seo` (basic), `draft_tweet`
- SSE log streaming
- One-page React frontend with terminal log + actions feed
- SQLite for now, no auth

### Week 2 — More tools, better content
- Tools: `analyze_competitor`, `draft_article`, `draft_reddit_reply`, `find_reddit_opportunities`
- Brand voice extraction from user writing samples
- Postgres + Supabase Auth
- Daily run scheduling (single cron for all users for now)
- Email digest (Resend)

### Week 3 — Integrations + polish
- Google PageSpeed (free, easy)
- PostHog (easy)
- Polished dashboard UI matching the Okara screenshots in feel but distinct
- Stripe Checkout for paid tiers
- Free tier gating

### Week 4 — Launch
- Google Analytics + Search Console OAuth
- Landing page emphasizing the OpenAdapter cost angle
- Launch on Product Hunt, HN ("Show HN: AI CMO that doesn't run on GPT-4")
- Twitter launch tweet from your own account

### Out of MVP scope (v2+)
- Auto-posting to platforms
- Multi-tenant team features
- Custom-tuned models per user
- Analytics correlation ("this Reddit reply drove 23 signups")
- Browser extension for one-click posting
- Discord / Slack integration
- A/B testing of content variants

---

## 12. Build Order (week 1 in detail)

Day 1 (4 hours):
- Repo setup: FastAPI + React monorepo or split repos
- OpenAdapter base URL test — make 3 LLM calls work
- Hello-world agent loop: one tool (`search_web`), prints thoughts

Day 2 (4 hours):
- `crawl_website` tool with Playwright
- `audit_seo` tool with PageSpeed API
- Persist run log to JSON file

Day 3 (4 hours):
- SSE streaming endpoint
- React frontend skeleton: terminal log component, actions feed component
- Wire frontend to backend, see live log streaming

Day 4 (4 hours):
- `draft_tweet` and `draft_article` tools with brand voice
- Brand voice extraction from sample text
- Action persistence

Day 5 (4 hours):
- `find_reddit_opportunities` + `draft_reddit_reply`
- This is the killer feature — spend extra time on prompt engineering for the reply quality

Day 6-7 (8 hours):
- Polish the first-dive flow (the magic moment)
- Self-test on openadapter.dev as the input — make sure it generates good actions for your own product

---

## 13. Naming Options

Brainstorm — pick one and commit:

**Marketing/Strategy theme:**
- `helmsman.ai` / `helm.cc` — steering your marketing
- `compass.cc` — direction-finder
- `northstar.cc` — North-star metric vibes
- `pulse.cc` / `getpulse.dev` — daily heartbeat for your product

**Agent/Operator theme:**
- `crow.cc` — the agent watching everything
- `siren.dev` — alerts and opportunities
- `oracle.cc` — predictions about your product
- `lookout.cc` — daily watch

**Function-direct:**
- `dailycmo.com` — descriptive
- `growthagent.dev` — descriptive  
- `marketing.bot` (.bot is ~$80 but memorable)

**OpenAdapter-tied (cross-promotion):**
- `cmo.openadapter.dev` — subdomain, no extra cost, ties products
- `agents.openadapter.dev` — broader story

**My picks:**
1. `pulse.cc` — short, brandable, "daily pulse" framing for the recurring run
2. `helm.cc` — captures "you're the captain, this steers" vibe
3. `cmo.openadapter.dev` — fastest to ship, free, strong cross-promo

The subdomain route is interesting because you can literally launch this as "OpenAdapter Agents — flagship use case of our gateway" and it boosts the parent brand.

---

## 14. Decisions Needed Before Building

1. **Product name + domain** — commit before week 1
2. **Standalone product or OpenAdapter feature?** — strategic call: do you sell this separately (more revenue, more support), or bundle it into OpenAdapter as a "we eat our own dogfood" demo (less direct revenue, more flywheel for OpenAdapter)? My lean: **launch standalone with the OpenAdapter wedge as marketing**, then later offer free tier to OpenAdapter customers.
3. **Agent framework:** Pydantic AI vs write-your-own. My lean: write your own first 2 weeks (200 LOC), migrate to Pydantic AI if needed.
4. **Cron vs queue:** for daily runs, simple cron works for <100 users; switch to Celery later.

---

## 15. Risks

1. **Okara raises and outspends you on ads.** Mitigation: lean into the "open / cheap / for indies" angle. They can't go cheaper without cannibalizing.
2. **Reddit shadow-bans your suggested replies.** Mitigation: copy-paste only (user posts from their own account), and aggressive prompt engineering against AI tells.
3. **Content quality plateaus and users churn.** Mitigation: real focus on brand voice training. The brand voice extraction is the moat — if your agent sounds like the user, switching cost is high.
4. **Google Analytics OAuth approval takes weeks.** Mitigation: launch with PostHog + Search Console first (faster approval), add GA later.
5. **LLM costs spike if a user runs the agent 100x/day.** Mitigation: rate-limit at the tier level, hard cap on tokens per run.

---

## 16. Why this matters beyond just this product

- It's a **flagship use case for OpenAdapter** — every story you tell about this product proves OpenAdapter's value
- It builds the muscle for **agent-based products**, which is where consumer + prosumer software is going
- It positions you as a builder who ships agents, not just "AI tools" — recruiting/credibility upside
- If it works, the same agent framework can power vertical-specific versions: AI CMO for SaaS, for newsletters, for ecom, for indie devs — each a separate launch
