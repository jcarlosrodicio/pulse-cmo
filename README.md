# Pulse

> Daily heartbeat for your product. An AI growth agent for indie founders — wakes up every morning, audits your site, scans HN for opportunities, drafts content in your voice, and hands you a daily action list. You spend 10 minutes copy-pasting; the agent does the rest.

Powered by [OpenAdapter](https://openadapter.dev) — runs on open-source models (MiniMax, GLM, DeepSeek) so a daily run costs cents, not dollars. Spec: [`ai-growth-agent-spec.md`](ai-growth-agent-spec.md).

## Status

MVP, end-to-end:

- ✅ Tool-calling agent loop with SSE streaming (ported from [`iris`](https://github.com/aruntemme/perso))
- ✅ Multi-provider LLM with failover (MiniMax-M2.5 → GLM-5.1 → GLM-5, all via OpenAdapter)
- ✅ 14 tools: `crawl_website`, `audit_seo`, `check_pagespeed`, `web_search`, `read_url`, `news_search`, `analyze_competitor`, `find_hn_opportunities`, `extract_brand_voice`, `draft_tweet`, `draft_hn_post`, `draft_linkedin_post`, `draft_article`, `generate_marketing_strategy`
- ✅ First-dive orchestrator (initial product scan, 7+ actions in one run)
- ✅ Daily orchestrator (recurring run, 3-5 fresh actions)
- ✅ APScheduler for daily cron
- ✅ SQLite store for projects / runs / actions
- ✅ Next.js dashboard with live terminal-style agent log + action feed
- ⏸ Reddit (intentionally deferred per the spec — copy-paste-only for MVP, and the prompt-engineering for non-spammy replies needs its own week)
- ⏸ Google Analytics / Search Console OAuth, PostHog (Tier 2)
- ⏸ Stripe / Auth / multi-tenant

## Quick start

```bash
# 1. install backend
uv sync
# (or:  uv venv && uv pip install -e .)

# 2. env — copy and put your OpenAdapter key in .env
cp .env.example .env

# 3. start backend
uv run pulse
# → http://127.0.0.1:8787

# 4. start frontend (new terminal)
cd web && npm install && npm run dev
# → http://localhost:3030
```

Open the frontend, enter a site URL, hit "First dive." Watch the agent crawl, audit, search HN, extract brand voice, and draft content live in the terminal log on the left; actions land on the right as they're generated.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Next.js (React 19, Tailwind 4) — :3030                       │
│  ├─ Onboarding (URL entry)                                    │
│  ├─ Dashboard: terminal log (SSE) + actions feed              │
│  └─ rewrites /api/* → backend                                 │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼  REST + SSE
┌──────────────────────────────────────────────────────────────┐
│  FastAPI (Python 3.12) — :8787                                │
│  ├─ /projects, /runs, /actions                                │
│  ├─ /runs/{id}/stream  (SSE replayable via RunBroker)         │
│  ├─ Agent loop (stream_chat → tool dispatch → loop)           │
│  └─ APScheduler (daily cron per project)                      │
└────────────────────────────┬─────────────────────────────────┘
                             │
              ┌──────────────┼────────────────┐
              ▼              ▼                ▼
        OpenAdapter      PageSpeed        HN Algolia
       /v1/tools/*       Insights API     (free, public)
       (search, scrape)
              │
              ▼
      MiniMax-M2.5 → GLM-5.1 → GLM-5 (failover)
```

## Layout

```
pulse.cc/
├── config.yaml              # providers, scheduler, agent settings
├── pyproject.toml
├── src/pulse/
│   ├── server.py            # FastAPI app, SSE, scheduler
│   ├── config.py
│   ├── llm.py               # multi-provider failover + retry
│   ├── agent.py             # tool-calling loop with streaming
│   ├── orchestrator.py      # first_dive / daily / manual run prompts
│   ├── tools/
│   │   ├── registry.py      # @tool decorator + schema gen (from iris)
│   │   ├── web.py           # OpenAdapter web_search / read_url / news
│   │   ├── crawl.py         # httpx + selectolax site crawler
│   │   ├── seo.py           # audit_seo + check_pagespeed
│   │   ├── discovery.py     # find_hn_opportunities
│   │   ├── drafting.py      # draft_tweet / draft_article / log_*
│   │   └── strategy.py      # brand_voice / marketing_strategy
│   └── store/
│       └── actions.py       # SQLite: projects, runs, actions
└── web/
    └── src/
        ├── app/
        │   ├── page.tsx     # onboarding ↔ dashboard
        │   └── globals.css
        ├── components/
        │   ├── Onboarding.tsx
        │   ├── Dashboard.tsx
        │   ├── TerminalLog.tsx  # the "live agent" log
        │   └── ActionCard.tsx   # one action with copy / ship / dismiss
        └── lib/
            └── api.ts       # typed client + SSE
```

## The OpenAdapter wedge

Every tool the agent uses routes through the same OpenAdapter API key:

- LLM calls: MiniMax-M2.5 (token-streams cleanly with tools), GLM-5.1 / GLM-5 as fallback.
- Web tools: `POST /v1/tools/search`, `/v1/tools/scrape/markdown`, `/v1/tools/search/news`.

This is the differentiator — a Pulse daily run costs ~$0.05-0.20 in tokens vs $1-5 for the same job on GPT-4o. Sustainable at $19/mo where Okara charges $99.

## Adding a tool

```python
# src/pulse/tools/your_tool.py
from .registry import Tool, tool

@tool
async def my_tool(query: str, limit: int = 5) -> str:
    """One-line description for the LLM.

    Args:
        query: What to search.
        limit: Max results.
    """
    ...
    return "result string"
```

Wire it into `orchestrator.build_registry_for_run` and (if relevant) reference it from the system prompt in `FIRST_DIVE_PROMPT` / `DAILY_PROMPT`.

## What's next

Per the spec, the path to "shippable to real users":

1. **Reddit replies** — proper anti-spam prompt + PRAW.
2. **Auth + multi-tenant** (Supabase Auth or Clerk).
3. **Stripe checkout** for paid tiers.
4. **GA / Search Console / PostHog** integrations (OAuth flows).
5. **Polished landing page** emphasizing the OpenAdapter cost story.
