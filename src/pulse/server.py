"""FastAPI server — REST endpoints + SSE streaming.

Endpoints:
  GET    /health
  POST   /projects                     — create project
  GET    /projects                     — list projects
  GET    /projects/{id}                — get project
  PATCH  /projects/{id}                — update project
  POST   /projects/{id}/runs           — start a run (kind=first_dive|daily|manual)
                                          returns {run_id, stream_url}
  GET    /runs/{id}                    — fetch run details + log
  GET    /runs/{id}/stream             — SSE stream of an in-progress run
  GET    /projects/{id}/actions        — list actions
  PATCH  /actions/{id}                 — update action status
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import Config
from .chat import expand_action_detail, stream_chat_reply
from .llm import LLM, usage_scope
from .log import setup_logging
from .launch import (
    attach_dates,
    classify_product,
    compute_scoreboard,
    default_intake,
    draft_launch_content,
    generate_launch_plan,
    infer_intake,
    launch_track_advice,
)
from .orchestrator import (
    run_first_dive,
    run_manual,
    run_targeted,
    run_weekly,
    run_weekly_review,
)
from .settings_store import SettingsStore
from .store import ActionStore
from .traction import scan_traction
from .versioning import create_version

log = structlog.get_logger()


# --- request models --------------------------------------------------------

class CreateProject(BaseModel):
    url: str
    name: str | None = None
    description: str = ""
    start_dive: bool = True


class UpdateProject(BaseModel):
    name: str | None = None
    url: str | None = None
    description: str | None = None
    competitors: list[str] | None = None
    schedule_hour: int | None = None
    schedule_minute: int | None = None
    schedule_times: list[str] | None = None   # ["06:00"] or ["06:00","18:00"]
    timezone: str | None = None
    writing_instructions: dict[str, Any] | None = None
    brief: dict[str, Any] | None = None        # the marketing brief (goal/icp/…)


class StartRun(BaseModel):
    kind: str = Field(pattern="^(first_dive|daily|weekly|weekly_review|manual|targeted)$")
    instruction: str = ""
    # For `kind="targeted"`: which channel to generate.
    target: str | None = Field(
        default=None,
        pattern="^(tweet|linkedin|hn_post|article|reddit_reply|reddit_opportunity|hn_opportunity|seo_audit|competitor_scan|market_gap|strategy)$",
    )
    topic: str = ""


class UpdateAction(BaseModel):
    status: str | None = Field(default=None, pattern="^(pending|shipped|dismissed)$")
    title: str | None = None
    content: str | None = None
    chosen_variant: int | None = None


class WeeklyReview(BaseModel):
    """The founder's weekly snapshot — the real signal the loop reads."""
    signups: str | None = None       # "12" or "12 (up from 7)"
    visitors: str | None = None
    top_sources: str = ""            # free text: "HN, 2 subreddits, direct"
    shipped: str = ""                # free text: what they actually did this week
    notes: str = ""


class GtmMoveDone(BaseModel):
    week_id: int
    index: int
    done: bool


class UpdateDocument(BaseModel):
    title: str | None = None
    content_md: str | None = None


class RegenerateDocument(BaseModel):
    kind: str = Field(pattern="^(product_information|competitor_analysis|brand_voice|marketing_strategy|positioning)$")


class CreateChatSession(BaseModel):
    title: str = "New conversation"


class RenameChatSession(BaseModel):
    title: str


class ChatMessage(BaseModel):
    content: str


class ProviderUpsert(BaseModel):
    name: str
    base_url: str
    api_key: str | None = None
    api_key_env: str | None = None
    model: str
    role: str = "fallback"
    timeout: float = 60.0
    max_retries: int = 1
    prompt_cost_per_million: float = 0.0
    completion_cost_per_million: float = 0.0


class SaveProviders(BaseModel):
    providers: list[ProviderUpsert]


class ProbeProvider(BaseModel):
    base_url: str
    api_key: str


# --- launch mode -----------------------------------------------------------

class StartLaunch(BaseModel):
    intake: dict[str, Any] | None = None


class UpdateLaunch(BaseModel):
    state: str | None = Field(default=None, pattern="^(intake|classify|plan|active|done)$")
    archetype: str | None = None
    intake: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    start_date: str | None = None


class GenerateLaunchPlan(BaseModel):
    # the archetype the user confirmed (may override the classifier)
    archetype: str


class LaunchAsset(BaseModel):
    target: str = Field(
        pattern="^(tweet|linkedin|hn_post|article|reddit_reply|reddit_opportunity|hn_opportunity)$"
    )
    topic: str = ""


class LaunchDraft(BaseModel):
    day_index: int
    piece_index: int


# --- run streaming infra ---------------------------------------------------

class RunBroker:
    """Pub/sub for live run events.

    Each in-progress run has a queue of subscribers. The orchestrator pushes
    events; SSE clients pop them. New subscribers also get a replay of events
    already buffered so reconnecting clients see the full log.
    """

    def __init__(self) -> None:
        self._buffers: dict[int, list[dict[str, Any]]] = {}
        self._subscribers: dict[int, list[asyncio.Queue]] = {}
        self._finished: set[int] = set()
        self._lock = asyncio.Lock()

    async def publish(self, run_id: int, event: dict[str, Any]) -> None:
        async with self._lock:
            self._buffers.setdefault(run_id, []).append(event)
            for q in self._subscribers.get(run_id, []):
                q.put_nowait(event)

    async def finish(self, run_id: int) -> None:
        async with self._lock:
            self._finished.add(run_id)
            for q in self._subscribers.get(run_id, []):
                q.put_nowait({"type": "_end"})

    def snapshot(self, run_id: int) -> list[dict[str, Any]]:
        """Read the current buffer without subscribing (polling fallback)."""
        return list(self._buffers.get(run_id, []))

    async def subscribe(self, run_id: int) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            for ev in self._buffers.get(run_id, []):
                q.put_nowait(ev)
            if run_id in self._finished:
                q.put_nowait({"type": "_end"})
            else:
                self._subscribers.setdefault(run_id, []).append(q)
        try:
            while True:
                ev = await q.get()
                if ev.get("type") == "_end":
                    return
                yield ev
        finally:
            async with self._lock:
                subs = self._subscribers.get(run_id) or []
                if q in subs:
                    subs.remove(q)


async def _execute_run(
    *,
    config: Config,
    llm: LLM,
    store: ActionStore,
    broker: RunBroker,
    project_id: int,
    run_id: int,
    kind: str,
    instruction: str = "",
    target: str | None = None,
    topic: str = "",
) -> None:
    log.info("run_start", run_id=run_id, project_id=project_id, kind=kind)
    captured: list[dict[str, Any]] = []
    iterations = 0
    status = "done"
    async with usage_scope() as tracker:
        try:
            if kind == "first_dive":
                stream = run_first_dive(
                    config=config, llm=llm, store=store, project_id=project_id, run_id=run_id
                )
            elif kind in ("weekly", "daily"):  # "daily" kept as a back-compat alias
                stream = run_weekly(
                    config=config, llm=llm, store=store, project_id=project_id, run_id=run_id
                )
            elif kind == "weekly_review":
                stream = run_weekly_review(
                    config=config, llm=llm, store=store, project_id=project_id,
                    run_id=run_id, instruction=instruction,
                )
            elif kind == "targeted":
                stream = run_targeted(
                    config=config,
                    llm=llm,
                    store=store,
                    project_id=project_id,
                    run_id=run_id,
                    target=target or "tweet",
                    topic=topic,
                    instruction=instruction,
                )
            else:
                stream = run_manual(
                    config=config,
                    llm=llm,
                    store=store,
                    project_id=project_id,
                    run_id=run_id,
                    instruction=instruction,
                )
            async for ev in stream:
                captured.append(ev)
                if ev.get("type") == "iteration":
                    iterations = max(iterations, int(ev.get("n", 0)))
                await broker.publish(run_id, ev)
        except Exception as e:
            status = "failed"
            err_ev = {"type": "error", "message": f"{type(e).__name__}: {e}"}
            captured.append(err_ev)
            await broker.publish(run_id, err_ev)
            log.exception("run_failed", run_id=run_id)
        finally:
            store.finish_run(
                run_id,
                status=status,
                iterations=iterations,
                log=captured,
                prompt_tokens=tracker.prompt_tokens,
                completion_tokens=tracker.completion_tokens,
                cost_usd=tracker.cost_usd,
            )
            store.record_usage(
                project_id,
                f"run:{kind}" + (f":{target}" if target else ""),
                tracker.prompt_tokens,
                tracker.completion_tokens,
                tracker.cost_usd,
            )
            done_event = {
                "type": "_done",
                "status": status,
                "prompt_tokens": tracker.prompt_tokens,
                "completion_tokens": tracker.completion_tokens,
                "total_tokens": tracker.total_tokens,
                "cost_usd": round(tracker.cost_usd, 6),
                "llm_calls": tracker.calls,
            }
            await broker.publish(run_id, done_event)
            await broker.finish(run_id)
            log.info(
                "run_end",
                run_id=run_id,
                status=status,
                iterations=iterations,
                tokens=tracker.total_tokens,
                cost_usd=round(tracker.cost_usd, 6),
            )
            # snapshot a version after a successful first dive / weekly review
            if status == "done" and kind in ("first_dive", "weekly_review"):
                try:
                    await create_version(
                        store=store, llm=llm, project_id=project_id, run_id=run_id, kind=kind
                    )
                except Exception:
                    log.exception("version_create_failed", run_id=run_id)


# --- app -------------------------------------------------------------------

def create_app(config: Config) -> FastAPI:
    setup_logging()
    db_path = config.data_path() / "pulse.db"
    store = ActionStore(db_path=db_path)
    settings = SettingsStore(config.data_path())
    settings.apply_to_config(config)
    llm = LLM(config)
    broker = RunBroker()
    scheduler = AsyncIOScheduler()

    background_tasks: set[asyncio.Task] = set()

    def _spawn(coro) -> None:
        t = asyncio.create_task(coro)
        background_tasks.add(t)
        t.add_done_callback(background_tasks.discard)

    async def _scheduled_weekly(project_id: int) -> None:
        """Scheduled lean refresh — rolls the GTM week forward only when stale, so
        it's safe to fire on the existing daily cron (it self-throttles to weekly)."""
        run_id = store.create_run(project_id, kind="weekly")
        await _execute_run(
            config=config,
            llm=llm,
            store=store,
            broker=broker,
            project_id=project_id,
            run_id=run_id,
            kind="weekly",
        )

    def _spawn_traction_scan(project_id: int) -> None:
        """Kick off a digital-footprint scan in the background (its own task, so
        it runs alongside a dive). Marks 'scanning' immediately so the Traction
        tab shows progress; failures are caught and surfaced as 'failed'."""
        store.set_traction_summary(
            project_id,
            {"status": "scanning", "started_at": datetime.now(timezone.utc).isoformat()},
        )

        async def _run() -> None:
            try:
                async with usage_scope() as t:
                    await scan_traction(config=config, llm=llm, store=store, project_id=project_id)
                _log_usage("traction", t, project_id)
            except Exception as e:
                log.exception("traction_scan_failed", project_id=project_id)
                store.set_traction_summary(
                    project_id, {"status": "failed", "error": f"{type(e).__name__}: {e}"}
                )

        _spawn(_run())

    def _schedule_project(project_id: int) -> None:
        """(Re)register one cron job per configured run time for a project."""
        # clear any existing jobs for this project (trailing '-' so project 1
        # doesn't match project 12's 'daily-12-0' jobs)
        for job in scheduler.get_jobs():
            if job.id and job.id.startswith(f"daily-{project_id}-"):
                scheduler.remove_job(job.id)
        proj = store.get_project(project_id) or {}
        times = proj.get("schedule_times")
        if not times:
            times = [f"{config.scheduler.daily_hour:02d}:{config.scheduler.daily_minute:02d}"]
        for i, t in enumerate(times):
            try:
                hh, mm = (int(x) for x in str(t).split(":")[:2])
            except (ValueError, TypeError):
                continue
            scheduler.add_job(
                _scheduled_weekly,
                CronTrigger(hour=hh, minute=mm),
                args=[project_id],
                id=f"daily-{project_id}-{i}",
                replace_existing=True,
            )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if config.scheduler.enabled:
            for proj in store.list_projects():
                _schedule_project(proj["id"])
            scheduler.start()
            log.info("scheduler_started", jobs=len(scheduler.get_jobs()))
        yield
        if config.scheduler.enabled:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="Pulse", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {
            "ok": True,
            "providers": [p.name for p in config.llm.providers],
            "data_dir": str(config.data_path()),
        }

    # --- projects ----------------------------------------------------------

    @app.post("/projects")
    async def create_project(body: CreateProject) -> dict:
        url = body.url.strip()
        if not url.startswith("http"):
            url = "https://" + url

        # Derive a sensible name from the host if not provided.
        derived_name = body.name
        if not derived_name:
            try:
                host = (urlparse(url).hostname or "").replace("www.", "")
                derived_name = host.split(".")[0].capitalize() if host else url
            except Exception:
                derived_name = url

        pid = store.create_project(
            name=derived_name, url=url, description=body.description
        )
        if config.scheduler.enabled:
            _schedule_project(pid)

        run_id: int | None = None
        if body.start_dive:
            run_id = store.create_run(pid, kind="first_dive")
            _spawn(
                _execute_run(
                    config=config,
                    llm=llm,
                    store=store,
                    broker=broker,
                    project_id=pid,
                    run_id=run_id,
                    kind="first_dive",
                )
            )
            _spawn_traction_scan(pid)

        proj = store.get_project(pid) or {}
        proj["initial_run_id"] = run_id
        return proj

    @app.get("/projects")
    async def list_projects() -> list[dict]:
        projects = store.list_projects()
        for p in projects:
            runs = store.list_runs(p["id"], limit=1)
            p["latest_run"] = runs[0] if runs else None
            p["active_run_id"] = (
                runs[0]["id"] if runs and runs[0]["status"] == "running" else None
            )
            p["action_counts"] = store.action_counts_by_type(p["id"], status="pending")
        return projects

    @app.get("/projects/{project_id}")
    async def get_project(project_id: int) -> dict:
        p = store.get_project(project_id)
        if not p:
            raise HTTPException(404, "project not found")
        runs = store.list_runs(project_id, limit=1)
        p["latest_run"] = runs[0] if runs else None
        p["active_run_id"] = (
            runs[0]["id"] if runs and runs[0]["status"] == "running" else None
        )
        p["action_counts"] = store.action_counts_by_type(project_id, status="pending")
        return p

    @app.patch("/projects/{project_id}")
    async def update_project(project_id: int, body: UpdateProject) -> dict:
        p = store.get_project(project_id)
        if not p:
            raise HTTPException(404, "project not found")
        store.update_project(
            project_id,
            **{k: v for k, v in body.model_dump(exclude_none=True).items()},
        )
        if config.scheduler.enabled and (
            body.schedule_hour is not None
            or body.schedule_minute is not None
            or body.schedule_times is not None
        ):
            _schedule_project(project_id)
        return store.get_project(project_id)

    @app.delete("/projects/{project_id}")
    async def delete_project(project_id: int) -> dict:
        """Complete wipe of a project and everything it owns. Irreversible."""
        if not store.get_project(project_id):
            raise HTTPException(404, "project not found")
        if config.scheduler.enabled:
            for job in scheduler.get_jobs():
                if job.id and job.id.startswith(f"daily-{project_id}-"):
                    scheduler.remove_job(job.id)
        store.delete_project(project_id)
        log.info("project_deleted", project_id=project_id)
        return {"ok": True, "deleted": project_id}

    @app.post("/projects/{project_id}/recon")
    async def recon_project(project_id: int) -> dict:
        """Fast pre-dive pass: crawl the site, persist the evidence, seed the
        name/description, and return a (blank) brief immediately. The smart
        pre-fill is a SEPARATE, async call (`/brief/suggest`) so a slow reasoning
        model never blocks the modal. Crawl-only, so this is quick and never 500s.
        """
        from .brief import default_brief
        from .tools.crawl import crawl_website, distill_crawl

        project = store.get_project(project_id)
        if not project:
            raise HTTPException(404, "project not found")

        crawl_summary: dict[str, Any] = {}
        crawl_ok = False
        try:
            raw = await crawl_website.fn(url=project["url"], max_pages=6)
            try:
                crawl_obj = json.loads(raw)
            except json.JSONDecodeError:
                crawl_obj = {"ok": False}
            crawl_ok = bool(crawl_obj.get("ok"))
            if crawl_ok:
                crawl_summary = distill_crawl(crawl_obj)
                store.set_crawl_summary(project_id, crawl_summary)
                # seed name/description from the crawl if they're still placeholder
                host_slug = (urlparse(project["url"]).hostname or "").split(".")[0].lower()
                updates: dict[str, Any] = {}
                if crawl_summary.get("description") and not project.get("description"):
                    updates["description"] = crawl_summary["description"][:300]
                if crawl_summary.get("title") and (project.get("name") or "").lower() in ("", host_slug):
                    updates["name"] = crawl_summary["title"].split("·")[0].split("|")[0].strip()[:80]
                if updates:
                    store.update_project(project_id, **updates)
                    project = store.get_project(project_id)
        except Exception as e:
            log.warning("recon_crawl_failed", project_id=project_id, error=repr(e))

        brief = store.get_brief(project_id) or default_brief()
        store.set_brief(project_id, brief)
        return {
            "brief": brief,
            "crawl": {
                "title": crawl_summary.get("title", ""),
                "description": crawl_summary.get("description", ""),
                "pages_fetched": crawl_summary.get("pages_fetched", 0),
                "ok": crawl_ok,
            },
            "project": store.get_project(project_id),
        }

    @app.post("/projects/{project_id}/brief/suggest")
    async def suggest_brief(project_id: int) -> dict:
        """The LLM pre-fill, called in the background after recon so the slow
        reasoning model never blocks the modal. Best-effort: returns only the
        inferable fields it could fill; on slowness/failure returns {}."""
        from .brief import infer_brief

        project = store.get_project(project_id)
        if not project:
            raise HTTPException(404, "project not found")
        crawl_text = (project.get("crawl_summary") or {}).get("text", "")
        suggested: dict[str, Any] = {}
        try:
            async with usage_scope() as t:
                brief = await asyncio.wait_for(
                    infer_brief(llm, project=project, crawl_text=crawl_text),
                    timeout=40.0,
                )
            _log_usage("brief_suggest", t, project_id)
            suggested = {
                k: brief.get(k)
                for k in ("goal_metric", "icp", "not_for", "wedge_hypothesis", "budget", "can_produce")
                if brief.get(k)
            }
            # merge into the stored brief so it persists even if the user waits
            stored = store.get_brief(project_id) or {}
            for k, v in suggested.items():
                if not stored.get(k):
                    stored[k] = v
            store.set_brief(project_id, stored)
        except Exception as e:
            log.warning("brief_suggest_failed", project_id=project_id, error=repr(e))
        return {"suggested": suggested}

    # --- runs --------------------------------------------------------------

    @app.post("/projects/{project_id}/runs")
    async def start_run(project_id: int, body: StartRun) -> dict:
        p = store.get_project(project_id)
        if not p:
            raise HTTPException(404, "project not found")
        run_id = store.create_run(project_id, kind=body.kind)
        _spawn(
            _execute_run(
                config=config,
                llm=llm,
                store=store,
                broker=broker,
                project_id=project_id,
                run_id=run_id,
                kind=body.kind,
                instruction=body.instruction,
                target=body.target,
                topic=body.topic,
            )
        )
        # a first dive also kicks off a traction scan in parallel, so the
        # digital-footprint map fills in alongside the dive
        if body.kind == "first_dive":
            _spawn_traction_scan(project_id)
        return {"run_id": run_id, "stream_url": f"/runs/{run_id}/stream"}

    @app.get("/runs/{run_id}")
    async def get_run(run_id: int) -> dict:
        r = store.get_run(run_id)
        if not r:
            raise HTTPException(404, "run not found")
        # while running, the persisted log is empty until finish; merge live buffer
        if r["status"] == "running":
            live = broker.snapshot(run_id)
            if live:
                r["log"] = live
        return r

    @app.get("/runs/{run_id}/stream")
    async def stream_run(run_id: int, request: Request) -> StreamingResponse:
        r = store.get_run(run_id)
        if not r:
            raise HTTPException(404, "run not found")

        async def gen() -> AsyncIterator[bytes]:
            async for ev in broker.subscribe(run_id):
                if await request.is_disconnected():
                    return
                yield f"data: {json.dumps(ev, default=str)}\n\n".encode("utf-8")
            yield b"data: {\"type\":\"_done\"}\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/projects/{project_id}/runs")
    async def list_project_runs(project_id: int) -> list[dict]:
        return store.list_runs(project_id)

    # --- GTM loop (the bet -> this week's moves -> the call) ---------------

    @app.get("/projects/{project_id}/gtm")
    async def get_gtm(project_id: int) -> dict:
        if not store.get_project(project_id):
            raise HTTPException(404, "project not found")
        return {
            "bet": store.get_channel_bet(project_id),
            "current_week": store.current_gtm_week(project_id),
            "weeks": store.list_gtm_weeks(project_id),
        }

    @app.post("/projects/{project_id}/weekly/review")
    async def submit_weekly_review(project_id: int, body: WeeklyReview) -> dict:
        """Log the week's real numbers -> Pulse makes the call + replans next
        week. Runs as a tracked run so it streams + shows in history like a dive."""
        if not store.get_project(project_id):
            raise HTTPException(404, "project not found")
        snapshot = {k: v for k, v in body.model_dump().items() if v not in (None, "")}
        run_id = store.create_run(project_id, kind="weekly_review")
        _spawn(
            _execute_run(
                config=config, llm=llm, store=store, broker=broker,
                project_id=project_id, run_id=run_id, kind="weekly_review",
                instruction=json.dumps(snapshot),
            )
        )
        return {"run_id": run_id, "stream_url": f"/runs/{run_id}/stream"}

    @app.post("/projects/{project_id}/gtm/move")
    async def set_gtm_move(project_id: int, body: GtmMoveDone) -> dict:
        if not store.get_project(project_id):
            raise HTTPException(404, "project not found")
        week = store.set_gtm_move_done(body.week_id, body.index, body.done)
        from .strategy_core import render_gtm_plan_doc
        render_gtm_plan_doc(store, project_id)  # keep the doc checkboxes in sync
        return {"week": week}

    # --- actions -----------------------------------------------------------

    @app.get("/projects/{project_id}/actions")
    async def list_actions(project_id: int, status: str | None = None) -> list[dict]:
        return store.list_actions(project_id, status=status)

    @app.patch("/actions/{action_id}")
    async def update_action(action_id: int, body: UpdateAction) -> dict:
        if body.status:
            store.update_action_status(action_id, body.status)
        if body.chosen_variant is not None:
            store.choose_action_variant(action_id, body.chosen_variant)
        if body.title is not None or body.content is not None:
            store.update_action_content(action_id, title=body.title, content=body.content)
        return store.get_action(action_id) or {"ok": True}

    @app.get("/actions/{action_id}")
    async def get_action(action_id: int) -> dict:
        a = store.get_action(action_id)
        if not a:
            raise HTTPException(404, "action not found")
        return a

    @app.post("/actions/{action_id}/expand")
    async def expand_action(action_id: int) -> dict:
        a = store.get_action(action_id)
        if not a:
            raise HTTPException(404, "action not found")
        async with usage_scope() as t:
            detail = await expand_action_detail(llm=llm, store=store, action_id=action_id)
        _log_usage("action_expand", t, a.get("project_id"))
        return {"action_id": action_id, "detail_md": detail}

    # --- documents ---------------------------------------------------------

    @app.get("/projects/{project_id}/documents")
    async def list_documents(project_id: int) -> list[dict]:
        return store.list_documents(project_id)

    @app.get("/projects/{project_id}/documents/{kind}")
    async def get_document_by_kind(project_id: int, kind: str) -> dict:
        doc = store.get_document_by_kind(project_id, kind)
        if not doc:
            raise HTTPException(404, "document not found")
        return doc

    @app.get("/documents/{document_id}")
    async def get_document(document_id: int) -> dict:
        doc = store.get_document(document_id)
        if not doc:
            raise HTTPException(404, "document not found")
        return doc

    @app.patch("/documents/{document_id}")
    async def update_document(document_id: int, body: UpdateDocument) -> dict:
        store.update_document(
            document_id, title=body.title, content_md=body.content_md
        )
        return store.get_document(document_id) or {"ok": True}

    @app.post("/projects/{project_id}/documents/regenerate")
    async def regenerate_document(project_id: int, body: RegenerateDocument) -> dict:
        from .chat import regenerate_document_for_project

        proj = store.get_project(project_id)
        if not proj:
            raise HTTPException(404, "project not found")
        doc_id = await regenerate_document_for_project(
            llm=llm, store=store, project_id=project_id, kind=body.kind
        )
        return store.get_document(doc_id) or {"ok": True}

    # --- chat sessions -----------------------------------------------------

    @app.post("/projects/{project_id}/chat/sessions")
    async def create_chat_session(project_id: int, body: CreateChatSession) -> dict:
        p = store.get_project(project_id)
        if not p:
            raise HTTPException(404, "project not found")
        sid = store.create_chat_session(project_id, title=body.title)
        return store.get_chat_session(sid)

    @app.get("/projects/{project_id}/chat/sessions")
    async def list_chat_sessions(project_id: int) -> list[dict]:
        return store.list_chat_sessions(project_id)

    @app.get("/chat/sessions/{session_id}")
    async def get_chat_session(session_id: int) -> dict:
        s = store.get_chat_session(session_id)
        if not s:
            raise HTTPException(404, "session not found")
        s["messages"] = store.list_chat_messages(session_id)
        return s

    @app.patch("/chat/sessions/{session_id}")
    async def rename_chat_session(session_id: int, body: RenameChatSession) -> dict:
        store.rename_chat_session(session_id, body.title)
        return store.get_chat_session(session_id) or {"ok": True}

    @app.delete("/chat/sessions/{session_id}")
    async def delete_chat_session(session_id: int) -> dict:
        store.delete_chat_session(session_id)
        return {"ok": True}

    @app.post("/chat/sessions/{session_id}/messages")
    async def post_chat_message(session_id: int, body: ChatMessage) -> StreamingResponse:
        sess = store.get_chat_session(session_id)
        if not sess:
            raise HTTPException(404, "session not found")
        project_id = sess["project_id"]

        async def gen() -> AsyncIterator[bytes]:
            try:
                async with usage_scope() as t:
                    async for ev in stream_chat_reply(
                        config=config,
                        llm=llm,
                        store=store,
                        project_id=project_id,
                        session_id=session_id,
                        user_message=body.content,
                    ):
                        yield f"data: {json.dumps(ev, default=str)}\n\n".encode("utf-8")
                _log_usage("chat", t, project_id)
            except Exception as e:
                log.exception("chat_stream_failed")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n".encode("utf-8")
            yield b"data: {\"type\":\"_done\"}\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # --- settings / provider config ----------------------------------------

    @app.get("/settings")
    async def get_settings() -> dict:
        providers = settings.list_providers(config.llm.providers)
        # don't echo back any API keys to the client (write-only)
        sanitized = [{**p, "api_key": "•••" if p.get("api_key") else None} for p in providers]
        return {
            "providers": sanitized,
            "default_temperature": config.llm.default_temperature,
            "max_iterations": config.agent.max_iterations,
        }

    @app.patch("/settings/providers")
    async def save_settings_providers(body: SaveProviders) -> dict:
        provider_dicts = [p.model_dump() for p in body.providers]
        # If client sent "•••" for api_key, treat as unchanged — preserve the
        # previously-stored value rather than wiping it.
        existing = {p["name"]: p for p in settings.load().get("providers", [])}
        for p in provider_dicts:
            if p.get("api_key") in ("•••", None, ""):
                p["api_key"] = existing.get(p["name"], {}).get("api_key")
        saved = settings.save_providers(provider_dicts)
        # hot-apply to running config
        settings.apply_to_config(config)
        llm._clients.clear()  # reset cached OpenAI clients
        return {"ok": True, "providers": [
            {**p, "api_key": "•••" if p.get("api_key") else None} for p in saved
        ]}

    @app.post("/settings/providers/probe")
    async def probe_provider(body: ProbeProvider) -> dict:
        return await settings.test_connection(
            base_url=body.base_url, api_key=body.api_key
        )

    @app.post("/settings/providers/fetch-models")
    async def fetch_models(body: ProbeProvider) -> dict:
        try:
            models = await settings.fetch_models(
                base_url=body.base_url, api_key=body.api_key
            )
            return {"ok": True, "models": models}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # --- launch mode -------------------------------------------------------

    def _require_project(project_id: int) -> dict:
        p = store.get_project(project_id)
        if not p:
            raise HTTPException(404, "project not found")
        return p

    def _log_usage(scope: str, tracker, project_id: int | None = None) -> None:
        store.record_usage(
            project_id, scope, tracker.prompt_tokens, tracker.completion_tokens, tracker.cost_usd
        )

    def _campaign_with_dates(project_id: int) -> dict | None:
        c = store.get_launch_campaign(project_id)
        if c and c.get("plan"):
            attach_dates(c["plan"], c.get("start_date"))
        return c

    @app.get("/projects/{project_id}/launch")
    async def get_launch(project_id: int) -> dict:
        _require_project(project_id)
        return {"campaign": _campaign_with_dates(project_id)}

    @app.post("/projects/{project_id}/launch")
    async def start_launch(project_id: int, body: StartLaunch) -> dict:
        """Start a launch: auto-infer intake from what Pulse already knows,
        then classify — all in one step. The founder confirms, doesn't fill
        out a form."""
        project = _require_project(project_id)
        if body.intake:
            intake = body.intake
        else:
            doc = store.get_document_by_kind(project_id, "product_information")
            product_md = (doc or {}).get("content_md", "") if doc else ""
            async with usage_scope() as t:
                intake = await infer_intake(llm, project=project, product_info_md=product_md)
            _log_usage("launch_infer", t, project_id)
        store.create_launch_campaign(project_id, state="intake", intake=intake)
        async with usage_scope() as t:
            result = await classify_product(llm, project=project, intake=intake)
        _log_usage("launch_classify", t, project_id)
        store.update_launch_campaign(
            project_id, state="classify", archetype=result["archetype"], classification=result
        )
        return {"classification": result, "campaign": store.get_launch_campaign(project_id)}

    @app.patch("/projects/{project_id}/launch")
    async def update_launch(project_id: int, body: UpdateLaunch) -> dict:
        _require_project(project_id)
        if not store.get_launch_campaign(project_id):
            raise HTTPException(404, "no launch campaign — start one first")
        fields = {k: v for k, v in body.model_dump(exclude_none=True).items()}
        store.update_launch_campaign(project_id, **fields)
        return {"campaign": _campaign_with_dates(project_id)}

    @app.post("/projects/{project_id}/launch/classify")
    async def classify_launch(project_id: int) -> dict:
        project = _require_project(project_id)
        campaign = store.get_launch_campaign(project_id)
        if not campaign:
            campaign = store.create_launch_campaign(
                project_id, intake=default_intake(project)
            )
        async with usage_scope() as t:
            result = await classify_product(
                llm, project=project, intake=campaign.get("intake") or {}
            )
        _log_usage("launch_classify", t, project_id)
        store.update_launch_campaign(
            project_id,
            state="classify",
            archetype=result["archetype"],
            classification=result,
        )
        return {"classification": result, "campaign": store.get_launch_campaign(project_id)}

    @app.post("/projects/{project_id}/launch/plan")
    async def make_launch_plan(project_id: int, body: GenerateLaunchPlan) -> dict:
        project = _require_project(project_id)
        campaign = store.get_launch_campaign(project_id)
        if not campaign:
            raise HTTPException(404, "no launch campaign — start one first")
        async with usage_scope() as t:
            plan = await generate_launch_plan(
                llm,
                project=project,
                archetype=body.archetype,
                intake=campaign.get("intake") or {},
            )
        _log_usage("launch_plan", t, project_id)
        store.update_launch_campaign(
            project_id, state="active", archetype=body.archetype, plan=plan
        )
        return {"plan": plan, "campaign": _campaign_with_dates(project_id)}

    @app.post("/projects/{project_id}/launch/draft")
    async def launch_draft(project_id: int, body: LaunchDraft) -> dict:
        """Generate the content for one day's content_piece inline, store the
        variants back on the plan, and return the updated piece."""
        _require_project(project_id)
        campaign = store.get_launch_campaign(project_id)
        if not campaign or not campaign.get("plan"):
            raise HTTPException(404, "no launch plan yet")
        plan = campaign["plan"]
        days = plan.get("days") or []
        if body.day_index < 0 or body.day_index >= len(days):
            raise HTTPException(400, "bad day_index")
        day = days[body.day_index]
        pieces = day.get("content_pieces") or []
        if body.piece_index < 0 or body.piece_index >= len(pieces):
            raise HTTPException(400, "bad piece_index")
        piece = pieces[body.piece_index]
        async with usage_scope() as t:
            result = await draft_launch_content(
                llm,
                store,
                project_id,
                kind=piece["kind"],
                brief=piece.get("brief", ""),
                day_title=day.get("title", ""),
            )
        _log_usage(f"launch_draft:{piece['kind']}", t, project_id)
        piece["status"] = "drafted"
        piece["variants"] = result["variants"]
        piece["chosen_variant"] = 0
        piece["action_id"] = result["action_id"]
        store.update_launch_campaign(project_id, plan=plan)
        return {"piece": piece, "day_index": body.day_index, "piece_index": body.piece_index}

    @app.post("/projects/{project_id}/launch/track")
    async def track_launch(project_id: int) -> dict:
        _require_project(project_id)
        campaign = store.get_launch_campaign(project_id)
        if not campaign or not campaign.get("plan"):
            raise HTTPException(404, "no launch plan yet")
        scoreboard = compute_scoreboard(campaign["plan"])
        async with usage_scope() as t:
            advice = await launch_track_advice(
                llm, plan=campaign["plan"], scoreboard=scoreboard
            )
        _log_usage("launch_track", t, project_id)
        return advice

    @app.post("/projects/{project_id}/launch/assets")
    async def launch_asset(project_id: int, body: LaunchAsset) -> dict:
        project = _require_project(project_id)
        run_id = store.create_run(project_id, kind="targeted")
        topic = body.topic or f"Launch-week content for {project.get('name')}"
        _spawn(
            _execute_run(
                config=config,
                llm=llm,
                store=store,
                broker=broker,
                project_id=project_id,
                run_id=run_id,
                kind="targeted",
                target=body.target,
                topic=topic,
            )
        )
        return {"run_id": run_id, "stream_url": f"/runs/{run_id}/stream"}

    @app.delete("/projects/{project_id}/launch")
    async def delete_launch(project_id: int) -> dict:
        _require_project(project_id)
        store.delete_launch_campaign(project_id)
        return {"ok": True}

    # --- traction (digital footprint) --------------------------------------

    @app.post("/projects/{project_id}/traction/scan")
    async def traction_scan(project_id: int) -> dict:
        _require_project(project_id)
        _spawn_traction_scan(project_id)
        return {"status": "scanning"}

    @app.get("/projects/{project_id}/traction")
    async def get_traction(project_id: int) -> dict:
        p = _require_project(project_id)
        return {"traction": p.get("traction_summary")}

    # --- GEO + links audits (on demand) ------------------------------------

    @app.post("/projects/{project_id}/audit/geo")
    async def audit_geo_now(project_id: int) -> dict:
        from .tools.geo import _audit_geo_impl
        p = _require_project(project_id)
        result = await _audit_geo_impl(p["url"])
        if result.get("ok"):
            store.set_geo_summary(project_id, result)
        return {"geo": store.get_project(project_id).get("geo_summary"), "result": result}

    @app.post("/projects/{project_id}/audit/links")
    async def audit_links_now(project_id: int) -> dict:
        from .tools.geo import _audit_links_impl
        p = _require_project(project_id)
        result = await _audit_links_impl(p["url"])
        if result.get("ok"):
            store.set_links_summary(project_id, result)
        return {"links": store.get_project(project_id).get("links_summary"), "result": result}

    # --- versions ----------------------------------------------------------

    @app.get("/projects/{project_id}/versions")
    async def list_versions(project_id: int) -> dict:
        _require_project(project_id)
        return {"versions": store.list_versions(project_id)}

    # --- usage -------------------------------------------------------------

    @app.get("/usage")
    async def get_usage(project_id: int | None = None) -> dict:
        return {
            "overall": store.usage_totals(),
            "project": store.usage_totals(project_id) if project_id is not None else None,
        }

    return app


def main() -> None:
    import uvicorn

    config_path = os.getenv("PULSE_CONFIG", "config.yaml")
    config = Config.load(config_path)

    # env overrides (for run.sh / Docker / any host)
    if os.getenv("PULSE_HOST"):
        config.server_host = os.environ["PULSE_HOST"]
    if os.getenv("PULSE_PORT"):
        config.server_port = int(os.environ["PULSE_PORT"])
    if os.getenv("PULSE_DATA_DIR"):
        config.data_dir = os.environ["PULSE_DATA_DIR"]

    app = create_app(config)
    uvicorn.run(
        app,
        host=config.server_host,
        port=config.server_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
