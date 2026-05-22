# Pulse — Architecture

How Pulse is built. For what it does see [Features](features.md).

---

## System overview

```
┌────────────────────────────────────────────────────────────────┐
│  Next.js 16 · React 19 · Tailwind 4   — :3030                   │
│  4-column dashboard · launch workspace · sheets (settings,      │
│  documents, versions) · live agent console (SSE)                │
│  next.config rewrites /api/* → backend                          │
└────────────────────────────┬────────────────────────────────────┘
                             │  REST (JSON) + SSE (text/event-stream)
┌────────────────────────────▼────────────────────────────────────┐
│  FastAPI · Python 3.12   — :8787                                │
│                                                                  │
│  server.py        endpoints, RunBroker (SSE pub/sub), scheduler  │
│  orchestrator.py  run prompts + tool registry per run            │
│  agent.py         the ReAct loop (stream → dispatch → repeat)    │
│  tools/*          @tool functions (crawl, seo, geo, web, …)      │
│  launch.py        archetypes, intake, plan, content              │
│  traction.py      footprint scan + synthesis                     │
│  versioning.py    per-run snapshot + day-over-day summary        │
│  chat.py          chat agent + document regeneration             │
│  llm.py           multi-provider failover + usage tracking       │
│  settings_store   runtime provider config (settings.json)        │
│  store/actions.py SQLite — single source of truth                │
└────────────────────────────┬────────────────────────────────────┘
              ┌──────────────┼───────────────┬──────────────┐
              ▼              ▼               ▼              ▼
        LLM provider     Web search /     Reddit JSON    HN Algolia
        (failover)       scrape (OA)      (public)       (public)
                                            ▲
                                   Google PageSpeed (optional)
```

Single-user, self-hosted, no auth. State lives in one SQLite file
(`~/.pulse/pulse.db`) plus `settings.json` next to it.

---

## The agent loop

`agent.py` runs a ReAct-style loop:

1. Send the conversation + the run's tool schemas to the model with streaming on.
2. Stream tokens out as `text` events; buffer any `tool_call`s.
3. When the model finishes a turn, dispatch each tool call through the registry,
   append results as `tool` messages, emit `tool_call` / `tool_result` events.
4. Repeat until the model stops calling tools or `max_iterations` is hit.

A `_ThinkFilter` strips `<think>…</think>` reasoning from the streamed text so it
never reaches the UI. Each iteration emits an `iteration` event used for the
console + the run's iteration count.

### Tools

A tool is a plain async function decorated with `@tool` (`tools/registry.py`).
The decorator reads the signature + Google-style docstring and produces the
OpenAI function schema — type hints become JSON-Schema, the docstring's `Args:`
become parameter descriptions. `ToolRegistry.dispatch(name, args)` calls it and
returns the result string the model sees.

Tools are bound per-run by `orchestrator.build_registry_for_run`, which wires in
the store + project_id so side-effecting tools (drafts, audits) persist directly.

---

## Run execution + streaming

- `server.start_run` (or the scheduler) creates an `agent_runs` row and spawns
  `_execute_run` as a background task.
- `_execute_run` opens a `usage_scope()`, picks the orchestrator coroutine for
  the run kind, and forwards every event to a **RunBroker**.
- **RunBroker** is an in-memory pub/sub keyed by run_id. It buffers events so a
  client connecting mid-run gets a full replay, and fans new events to all
  subscribers. `GET /runs/{id}/stream` is an SSE subscription; the buffer also
  backs a polling fallback (`GET /runs/{id}` merges the live buffer).
- On finish: persist the log + tokens + cost to `agent_runs`, emit a `_done`
  event with usage, record a usage-ledger event, and (for first_dive/daily)
  snapshot a version.

The frontend's `useRunStream` hook prefers SSE and falls back to 3s polling, so
the console + feed stay live even if the stream drops.

---

## Data model (SQLite)

| Table | Purpose |
|---|---|
| `projects` | one row per product. Scalar fields + JSON blobs: `competitors`, `brand_voice`, `writing_instructions`, `pagespeed_summary`, `seo_summary`, `geo_summary`, `links_summary`, `traction_summary`, `schedule_times` |
| `agent_runs` | every run: kind, status, iterations, tokens, `cost_micros`, JSON log |
| `actions` | the feed: type, title, content, `context` (variants, source url, severity…), status, `detail_md` |
| `documents` | Product Information / Competitor Analysis / Brand Voice / Marketing Strategy (markdown) |
| `chat_sessions` / `chat_messages` | per-project chat history |
| `launch_campaigns` | one per project: state, archetype, intake, plan (the Week-1 board), start_date |
| `project_versions` | per-run snapshot + comparison summary, auto-incrementing `version_num` |
| `usage_events` | the usage ledger: scope, prompt/completion tokens, `cost_micros` |

Migrations are forward-only and idempotent (`_migrate` wraps each `ALTER TABLE`
to ignore "duplicate column"). Money is stored as `cost_micros` (USD × 1e6) for
integer precision. JSON columns are hydrated on read.

---

## LLM layer + failover

`llm.py` wraps OpenAI-compatible chat completions with:

- **Provider failover** — providers are tried in order; on error the next is
  used. Roles (primary / secondary / fallback / vision) order the list.
- **Retry** — tenacity retries transient errors (timeouts, rate limits, 5xx)
  per provider before failing over.
- **Streaming** — `stream_chat` yields deltas + a final usage chunk
  (`stream_options.include_usage`).
- **Usage tracking** — a `usage_scope()` context manager + a `contextvars`
  tracker accumulate tokens + cost across all calls in the scope, isolated
  across concurrent runs. `_execute_run` and each LLM-using endpoint open a
  scope and record the total to `usage_events`.
- `strip_reasoning()` removes `<think>` blocks from completions.

Providers come from `config.yaml`, then are overlaid by `settings_store` (the
runtime Settings → Providers panel), which writes `settings.json` and re-applies
to the live config (clearing the cached clients).

---

## Subsystems

- **launch.py** — the `ARCHETYPES` table is the IP: each archetype fixes growth
  engine, north-star, ordered channels (tagged repeatable/one-shot), and
  anti-patterns. `infer_intake` reads the product doc, `classify_product` maps to
  an archetype, `generate_launch_plan` renders the Week-1 board, `draft_launch_
  content` produces variants via the shared founder-voice machinery, and
  `compute_scoreboard` / `launch_track_advice` drive the tracker.
- **traction.py** — fan-out search + URL→platform classification (pure) + one
  LLM synthesis pass for strength/sentiment/insights. Cached on the project.
- **versioning.py** — `snapshot_project` (pure read) + `_diff` (machine deltas) +
  an LLM comparison note; falls back to a deterministic summary if the call fails.
- **tools/geo.py** — `audit_geo` parses robots.txt for AI-crawler tokens and
  checks llms.txt / schema / headings; `audit_links` extracts + HEAD-checks links.

---

## Frontend

- `app/page.tsx` — top-level state (projects, active project, run stream); wires
  the Shell + all sheets (settings, documents, versions, launch, writing
  instructions).
- `app/tokens.css` — the design system: CSS variables for dark/light themes.
  Components reference `var(--…)`, never hardcoded hex.
- `lib/api.ts` — the typed client + the SSE helper.
- `hooks/useRunStream.ts` — SSE subscription with a polling fallback.
- Components are grouped by feature: `layout/`, `actions/`, `analytics/`,
  `launch/`, `versions/`, `settings/`, `chat/`, `company/`, `ui/`.

The frontend never calls the LLM or external services directly — everything goes
through `/api/*`, which `next.config.ts` rewrites to the backend (the URL is a
build arg in Docker, since Next bakes the rewrite destination at build time).

---

## Deployment

- **Dev**: `./run.sh` (installs + runs both) or run backend (`uv run pulse`) and
  frontend (`npm run dev`) separately.
- **Docker**: `docker compose up --build` — backend image (`python:3.12-slim` +
  uv, db in a `/data` volume) + frontend image (multi-stage Next.js standalone).
  The frontend proxies `/api/*` to the `backend` service over the compose network.
- **Env overrides**: `PULSE_HOST`, `PULSE_PORT`, `PULSE_DATA_DIR`, `PULSE_CONFIG`.

---

## Adding a tool

```python
# src/pulse/tools/your_tool.py
from .registry import tool

@tool
async def my_tool(query: str, limit: int = 5) -> str:
    """One-line description the model reads to decide when to call this.

    Args:
        query: What to search for.
        limit: Max results (default 5).
    """
    return "result string the model sees"
```

Register it in `orchestrator.build_registry_for_run` and reference it from the
relevant run prompt. If it should persist to the project, accept `store` +
`project_id` via a `make_*_tools(store, project_id)` factory (see `tools/seo.py`).
