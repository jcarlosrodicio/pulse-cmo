"""SQLite store for projects, agent runs, actions, and chat sessions.

Single-user MVP — no auth, no row-level security, just a local db.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT,
    brand_voice TEXT,             -- json
    competitors TEXT,             -- json array of strings
    schedule_hour INTEGER DEFAULT 6,
    schedule_minute INTEGER DEFAULT 0,
    timezone TEXT DEFAULT 'UTC',
    writing_instructions TEXT,    -- json: per-channel writing rules
    pagespeed_summary TEXT,       -- json: cached PageSpeed scores
    seo_summary TEXT,             -- json: cached audit_seo summary
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    kind TEXT NOT NULL,           -- 'first_dive' | 'daily' | 'manual'
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,         -- 'running' | 'done' | 'failed'
    total_iterations INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost_micros INTEGER DEFAULT 0,   -- cost in millionths of USD (1e-6 precision)
    log TEXT,                     -- json array of events
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    run_id INTEGER,
    action_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    context TEXT,
    detail_md TEXT,               -- expanded markdown guide (lazy-generated)
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    shipped_at TEXT,
    source_url TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (run_id) REFERENCES agent_runs(id)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT 'New conversation',
    created_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,           -- 'user' | 'assistant'
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    kind TEXT NOT NULL,         -- 'product_information' | 'competitor_analysis' | 'brand_voice' | 'marketing_strategy'
    title TEXT NOT NULL,
    content_md TEXT NOT NULL,
    metadata TEXT,              -- json blob, kind-specific
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    UNIQUE (project_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_actions_project_status ON actions(project_id, status);
CREATE INDEX IF NOT EXISTS idx_actions_project_type ON actions(project_id, action_type);
CREATE INDEX IF NOT EXISTS idx_runs_project ON agent_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON chat_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate(conn: sqlite3.Connection) -> None:
    """Lightweight forward-only migrations for columns added after v0.1.

    Idempotent — each ALTER is wrapped to ignore 'duplicate column'."""

    extra_columns = [
        ("projects", "writing_instructions", "TEXT"),
        ("projects", "pagespeed_summary", "TEXT"),
        ("projects", "seo_summary", "TEXT"),
        ("actions", "detail_md", "TEXT"),
        ("agent_runs", "prompt_tokens", "INTEGER DEFAULT 0"),
        ("agent_runs", "completion_tokens", "INTEGER DEFAULT 0"),
        ("agent_runs", "cost_micros", "INTEGER DEFAULT 0"),
    ]
    for table, col, ctype in extra_columns:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")
        except sqlite3.OperationalError:
            pass  # already there


class ActionStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            _migrate(conn)

    # --- projects -----------------------------------------------------------

    def create_project(self, *, name: str, url: str, description: str = "") -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO projects (name, url, description, competitors, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, url, description, json.dumps([]), _now()),
            )
            return int(cur.lastrowid)

    def get_project(self, project_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return _hydrate_project(row)

    def list_projects(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [p for p in (_hydrate_project(r) for r in rows) if p is not None]

    def update_project(self, project_id: int, **fields: Any) -> None:
        scalar = {
            "name",
            "url",
            "description",
            "schedule_hour",
            "schedule_minute",
            "timezone",
        }
        json_fields = {"competitors", "writing_instructions", "pagespeed_summary", "seo_summary", "brand_voice"}
        sets, vals = [], []
        for k, v in fields.items():
            if k in scalar:
                sets.append(f"{k}=?")
                vals.append(v)
            elif k in json_fields:
                sets.append(f"{k}=?")
                vals.append(json.dumps(v) if v is not None else None)
        if not sets:
            return
        vals.append(project_id)
        with self._lock, self._conn() as conn:
            conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", vals)

    def set_brand_voice(self, project_id: int, voice: dict[str, Any]) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE projects SET brand_voice=? WHERE id=?",
                (json.dumps(voice), project_id),
            )

    def get_brand_voice(self, project_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT brand_voice FROM projects WHERE id=?", (project_id,)
            ).fetchone()
        if not row or not row["brand_voice"]:
            return None
        return json.loads(row["brand_voice"])

    def set_pagespeed_summary(self, project_id: int, summary: dict[str, Any]) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE projects SET pagespeed_summary=? WHERE id=?",
                (json.dumps(summary), project_id),
            )

    def set_seo_summary(self, project_id: int, summary: dict[str, Any]) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE projects SET seo_summary=? WHERE id=?",
                (json.dumps(summary), project_id),
            )

    # --- runs ---------------------------------------------------------------

    def create_run(self, project_id: int, kind: str) -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO agent_runs (project_id, kind, started_at, status, log) "
                "VALUES (?, ?, ?, 'running', '[]')",
                (project_id, kind, _now()),
            )
            return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        iterations: int,
        log: list[dict[str, Any]],
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        cost_micros = int(round(cost_usd * 1_000_000))
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE agent_runs SET finished_at=?, status=?, total_iterations=?, "
                "prompt_tokens=?, completion_tokens=?, cost_micros=?, log=? "
                "WHERE id=?",
                (
                    _now(),
                    status,
                    iterations,
                    prompt_tokens,
                    completion_tokens,
                    cost_micros,
                    json.dumps(log),
                    run_id,
                ),
            )

    def latest_run_id(self, project_id: int) -> int | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM agent_runs WHERE project_id=? ORDER BY id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return int(row["id"]) if row else None

    def list_runs(self, project_id: int, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, kind, started_at, finished_at, status, total_iterations, "
                "prompt_tokens, completion_tokens, cost_micros "
                "FROM agent_runs WHERE project_id=? ORDER BY id DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [_hydrate_run_row(dict(r)) for r in rows]

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["log"] = json.loads(d["log"]) if d["log"] else []
        return _hydrate_run_row(d)

    # --- actions ------------------------------------------------------------

    def create_action(
        self,
        *,
        project_id: int,
        run_id: int,
        action_type: str,
        title: str,
        content: str,
        context: dict[str, Any] | None = None,
    ) -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO actions (project_id, run_id, action_type, title, content, context, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    run_id or None,
                    action_type,
                    title,
                    content,
                    json.dumps(context or {}),
                    _now(),
                ),
            )
            return int(cur.lastrowid)

    def list_actions(
        self,
        project_id: int,
        *,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        q = "SELECT * FROM actions WHERE project_id=?"
        params: list[Any] = [project_id]
        if status:
            q += " AND status=?"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(q, params).fetchall()
        return [_hydrate_action(r) for r in rows]

    def get_action(self, action_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
        return _hydrate_action(row) if row else None

    def update_action_status(self, action_id: int, status: str) -> None:
        if status not in ("pending", "shipped", "dismissed"):
            raise ValueError(f"bad status: {status}")
        shipped_at = _now() if status == "shipped" else None
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE actions SET status=?, shipped_at=? WHERE id=?",
                (status, shipped_at, action_id),
            )

    def update_action_content(self, action_id: int, *, title: str | None = None, content: str | None = None) -> None:
        sets, vals = [], []
        if title is not None:
            sets.append("title=?")
            vals.append(title)
        if content is not None:
            sets.append("content=?")
            vals.append(content)
        if not sets:
            return
        vals.append(action_id)
        with self._lock, self._conn() as conn:
            conn.execute(f"UPDATE actions SET {', '.join(sets)} WHERE id=?", vals)

    def choose_action_variant(self, action_id: int, index: int) -> None:
        """Pick which variant is the active draft. Mirrors variants[i] into content.

        No-op if the action has no variants or index is out of range.
        """
        action = self.get_action(action_id)
        if not action:
            return
        ctx = dict(action.get("context") or {})
        variants = ctx.get("variants") or []
        if not isinstance(variants, list) or len(variants) == 0:
            return
        i = max(0, min(int(index), len(variants) - 1))
        ctx["chosen_variant"] = i
        new_content = str(variants[i])
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE actions SET content=?, context=? WHERE id=?",
                (new_content, json.dumps(ctx), action_id),
            )

    def set_action_detail(self, action_id: int, detail_md: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE actions SET detail_md=? WHERE id=?", (detail_md, action_id)
            )

    def action_counts_by_type(self, project_id: int, *, status: str = "pending") -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT action_type, COUNT(*) as n FROM actions "
                "WHERE project_id=? AND status=? GROUP BY action_type",
                (project_id, status),
            ).fetchall()
        return {r["action_type"]: r["n"] for r in rows}

    # --- chat sessions ------------------------------------------------------

    def create_chat_session(self, project_id: int, *, title: str = "New conversation") -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO chat_sessions (project_id, title, created_at, last_activity_at) "
                "VALUES (?, ?, ?, ?)",
                (project_id, title, _now(), _now()),
            )
            return int(cur.lastrowid)

    def list_chat_sessions(self, project_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT s.id, s.project_id, s.title, s.created_at, s.last_activity_at, "
                "(SELECT COUNT(*) FROM chat_messages m WHERE m.session_id=s.id) as message_count "
                "FROM chat_sessions s WHERE s.project_id=? ORDER BY s.last_activity_at DESC",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_chat_session(self, session_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE id=?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def rename_chat_session(self, session_id: int, title: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE chat_sessions SET title=? WHERE id=?", (title, session_id)
            )

    def delete_chat_session(self, session_id: int) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))

    def list_chat_messages(self, session_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE session_id=? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- documents ----------------------------------------------------------

    def upsert_document(
        self,
        *,
        project_id: int,
        kind: str,
        title: str,
        content_md: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        meta_json = json.dumps(metadata or {})
        with self._lock, self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM documents WHERE project_id=? AND kind=?",
                (project_id, kind),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE documents SET title=?, content_md=?, metadata=?, updated_at=? WHERE id=?",
                    (title, content_md, meta_json, _now(), existing["id"]),
                )
                return int(existing["id"])
            cur = conn.execute(
                "INSERT INTO documents (project_id, kind, title, content_md, metadata, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project_id, kind, title, content_md, meta_json, _now(), _now()),
            )
            return int(cur.lastrowid)

    def list_documents(self, project_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE project_id=? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        return [_hydrate_document(r) for r in rows]

    def get_document(self, document_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        return _hydrate_document(row) if row else None

    def get_document_by_kind(self, project_id: int, kind: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE project_id=? AND kind=?",
                (project_id, kind),
            ).fetchone()
        return _hydrate_document(row) if row else None

    def update_document(
        self,
        document_id: int,
        *,
        title: str | None = None,
        content_md: str | None = None,
    ) -> None:
        sets, vals = [], []
        if title is not None:
            sets.append("title=?")
            vals.append(title)
        if content_md is not None:
            sets.append("content_md=?")
            vals.append(content_md)
        if not sets:
            return
        sets.append("updated_at=?")
        vals.append(_now())
        vals.append(document_id)
        with self._lock, self._conn() as conn:
            conn.execute(f"UPDATE documents SET {', '.join(sets)} WHERE id=?", vals)

    # --- chat messages ------------------------------------------------------

    def add_chat_message(self, session_id: int, role: str, content: str) -> int:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, _now()),
            )
            conn.execute(
                "UPDATE chat_sessions SET last_activity_at=? WHERE id=?",
                (_now(), session_id),
            )
            return int(cur.lastrowid)


def _hydrate_project(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    d = dict(row)
    d["competitors"] = json.loads(d["competitors"]) if d.get("competitors") else []
    d["brand_voice"] = json.loads(d["brand_voice"]) if d.get("brand_voice") else None
    d["writing_instructions"] = (
        json.loads(d["writing_instructions"]) if d.get("writing_instructions") else None
    )
    d["pagespeed_summary"] = (
        json.loads(d["pagespeed_summary"]) if d.get("pagespeed_summary") else None
    )
    d["seo_summary"] = json.loads(d["seo_summary"]) if d.get("seo_summary") else None
    return d


def _hydrate_run_row(d: dict[str, Any]) -> dict[str, Any]:
    """Augment a raw agent_runs dict with derived fields the UI needs."""
    micros = d.get("cost_micros") or 0
    d["cost_usd"] = micros / 1_000_000.0
    d["total_tokens"] = (d.get("prompt_tokens") or 0) + (d.get("completion_tokens") or 0)
    return d


def _hydrate_action(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["context"] = json.loads(d["context"]) if d.get("context") else {}
    return d


def _hydrate_document(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    d = dict(row)
    d["metadata"] = json.loads(d["metadata"]) if d.get("metadata") else {}
    return d
