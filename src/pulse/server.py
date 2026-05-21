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
    classify_product,
    compute_scoreboard,
    default_intake,
    generate_launch_plan,
    launch_track_advice,
)
from .orchestrator import run_daily, run_first_dive, run_manual, run_targeted
from .settings_store import SettingsStore
from .store import ActionStore

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
    timezone: str | None = None
    writing_instructions: dict[str, Any] | None = None


class StartRun(BaseModel):
    kind: str = Field(pattern="^(first_dive|daily|manual|targeted)$")
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


class UpdateDocument(BaseModel):
    title: str | None = None
    content_md: str | None = None


class RegenerateDocument(BaseModel):
    kind: str = Field(pattern="^(product_information|competitor_analysis|brand_voice|marketing_strategy)$")


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
            elif kind == "daily":
                stream = run_daily(
                    config=config, llm=llm, store=store, project_id=project_id, run_id=run_id
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

    async def _daily_for_project(project_id: int) -> None:
        run_id = store.create_run(project_id, kind="daily")
        await _execute_run(
            config=config,
            llm=llm,
            store=store,
            broker=broker,
            project_id=project_id,
            run_id=run_id,
            kind="daily",
        )

    def _schedule_daily(project_id: int, hour: int, minute: int) -> None:
        scheduler.add_job(
            _daily_for_project,
            CronTrigger(hour=hour, minute=minute),
            args=[project_id],
            id=f"daily-{project_id}",
            replace_existing=True,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if config.scheduler.enabled:
            for proj in store.list_projects():
                _schedule_daily(
                    proj["id"],
                    int(proj.get("schedule_hour") or config.scheduler.daily_hour),
                    int(proj.get("schedule_minute") or config.scheduler.daily_minute),
                )
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
            _schedule_daily(pid, config.scheduler.daily_hour, config.scheduler.daily_minute)

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
            body.schedule_hour is not None or body.schedule_minute is not None
        ):
            updated = store.get_project(project_id)
            _schedule_daily(
                project_id,
                int(updated.get("schedule_hour") or config.scheduler.daily_hour),
                int(updated.get("schedule_minute") or config.scheduler.daily_minute),
            )
        return store.get_project(project_id)

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
        detail = await expand_action_detail(llm=llm, store=store, action_id=action_id)
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
                async for ev in stream_chat_reply(
                    config=config,
                    llm=llm,
                    store=store,
                    project_id=project_id,
                    session_id=session_id,
                    user_message=body.content,
                ):
                    yield f"data: {json.dumps(ev, default=str)}\n\n".encode("utf-8")
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

    @app.get("/projects/{project_id}/launch")
    async def get_launch(project_id: int) -> dict:
        _require_project(project_id)
        campaign = store.get_launch_campaign(project_id)
        return {"campaign": campaign}

    @app.post("/projects/{project_id}/launch")
    async def start_launch(project_id: int, body: StartLaunch) -> dict:
        project = _require_project(project_id)
        intake = body.intake or default_intake(project)
        campaign = store.create_launch_campaign(project_id, state="intake", intake=intake)
        return {"campaign": campaign}

    @app.patch("/projects/{project_id}/launch")
    async def update_launch(project_id: int, body: UpdateLaunch) -> dict:
        _require_project(project_id)
        if not store.get_launch_campaign(project_id):
            raise HTTPException(404, "no launch campaign — start one first")
        fields = {k: v for k, v in body.model_dump(exclude_none=True).items()}
        campaign = store.update_launch_campaign(project_id, **fields)
        return {"campaign": campaign}

    @app.post("/projects/{project_id}/launch/classify")
    async def classify_launch(project_id: int) -> dict:
        project = _require_project(project_id)
        campaign = store.get_launch_campaign(project_id)
        if not campaign:
            campaign = store.create_launch_campaign(
                project_id, intake=default_intake(project)
            )
        async with usage_scope():
            result = await classify_product(
                llm, project=project, intake=campaign.get("intake") or {}
            )
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
        async with usage_scope():
            plan = await generate_launch_plan(
                llm,
                project=project,
                archetype=body.archetype,
                intake=campaign.get("intake") or {},
            )
        store.update_launch_campaign(
            project_id, state="active", archetype=body.archetype, plan=plan
        )
        return {"plan": plan, "campaign": store.get_launch_campaign(project_id)}

    @app.post("/projects/{project_id}/launch/track")
    async def track_launch(project_id: int) -> dict:
        _require_project(project_id)
        campaign = store.get_launch_campaign(project_id)
        if not campaign or not campaign.get("plan"):
            raise HTTPException(404, "no launch plan yet")
        scoreboard = compute_scoreboard(campaign["plan"])
        async with usage_scope():
            advice = await launch_track_advice(
                llm, plan=campaign["plan"], scoreboard=scoreboard
            )
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

    return app


def main() -> None:
    import uvicorn

    config_path = os.getenv("PULSE_CONFIG", "config.yaml")
    config = Config.load(config_path)
    app = create_app(config)
    uvicorn.run(
        app,
        host=config.server_host,
        port=config.server_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
