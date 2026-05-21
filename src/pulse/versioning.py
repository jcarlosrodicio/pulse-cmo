"""Project versioning — each completed run snapshots the project's state and
generates a short day-over-day comparison summary.

A "version" is a point-in-time read of what Pulse knows + produced: action
counts, SEO score, traction footprint, and the run's cost. Comparing
consecutive versions gives the founder a changelog of their growth.
"""

from __future__ import annotations

from typing import Any

import structlog

from .llm import LLM, Message

log = structlog.get_logger()


def snapshot_project(store: Any, project_id: int, run_id: int | None) -> dict[str, Any]:
    """Pure read of the project's current state for a version record."""
    project = store.get_project(project_id) or {}
    actions = store.list_actions(project_id)

    by_type: dict[str, int] = {}
    for a in actions:
        by_type[a["action_type"]] = by_type.get(a["action_type"], 0) + 1

    new_this_run = sum(1 for a in actions if run_id and a.get("run_id") == run_id)

    seo = project.get("seo_summary") or {}
    traction = project.get("traction_summary") or {}

    run = store.get_run(run_id) if run_id else None

    return {
        "actions_total": len(actions),
        "actions_by_type": by_type,
        "actions_new": new_this_run,
        "seo_score": seo.get("score"),
        "traction_mentions": (traction.get("totals") or {}).get("mentions"),
        "traction_strongest": traction.get("strongest"),
        "cost_usd": round((run or {}).get("cost_usd", 0.0), 4) if run else 0.0,
        "total_tokens": (run or {}).get("total_tokens") if run else None,
        "iterations": (run or {}).get("total_iterations") if run else None,
    }


def _diff(curr: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, Any]:
    """Compute machine deltas between two snapshots (no LLM)."""
    prev = prev or {}
    def n(d: dict, k: str) -> float:
        v = d.get(k)
        return float(v) if isinstance(v, (int, float)) else 0.0
    return {
        "actions_delta": int(n(curr, "actions_total") - n(prev, "actions_total")),
        "seo_delta": (
            round(n(curr, "seo_score") - n(prev, "seo_score"))
            if curr.get("seo_score") is not None and prev.get("seo_score") is not None
            else None
        ),
        "traction_delta": (
            int(n(curr, "traction_mentions") - n(prev, "traction_mentions"))
            if curr.get("traction_mentions") is not None and prev.get("traction_mentions") is not None
            else None
        ),
    }


_SUMMARY_PROMPT = """\
You write a one-paragraph "what changed" note for a founder, comparing today's
snapshot of their marketing to the previous one. Be concrete and short (2-3
sentences max). Lead with what's new or moved. No preamble, no marketing fluff,
no em-dashes. If this is the first version, just describe the starting point in
one sentence. Output plain text only.\
"""


async def create_version(
    *, store: Any, llm: LLM, project_id: int, run_id: int | None, kind: str
) -> dict[str, Any]:
    """Snapshot the project and store a version with an LLM comparison summary."""
    curr = snapshot_project(store, project_id, run_id)
    prev_version = store.latest_version(project_id)
    prev = (prev_version or {}).get("snapshot")
    deltas = _diff(curr, prev)
    curr["deltas"] = deltas

    project = store.get_project(project_id) or {}
    new_actions = curr.get("actions_new", 0)

    if prev is None:
        summary = (
            f"Baseline version for {project.get('name')}. "
            f"{curr['actions_total']} actions ready"
            + (f", SEO score {curr['seo_score']}/100" if curr.get("seo_score") is not None else "")
            + (f", {curr['traction_mentions']} mentions across the web" if curr.get("traction_mentions") is not None else "")
            + "."
        )
    else:
        user = (
            f"PRODUCT: {project.get('name')}\n"
            f"RUN: {kind}, {new_actions} new actions this run\n\n"
            f"PREVIOUS SNAPSHOT:\n{prev}\n\n"
            f"CURRENT SNAPSHOT:\n{curr}\n\n"
            f"MACHINE DELTAS: {deltas}\n\n"
            "Write the 'what changed' note."
        )
        try:
            summary = (await llm.complete(
                [Message(role="system", content=_SUMMARY_PROMPT), Message(role="user", content=user)],
                temperature=0.4,
                max_tokens=300,
            )).strip()
        except Exception as e:
            log.warning("version_summary_failed", error=repr(e))
            # graceful, deterministic fallback
            bits = []
            if new_actions:
                bits.append(f"{new_actions} new action{'s' if new_actions != 1 else ''}")
            if deltas.get("seo_delta"):
                bits.append(f"SEO {'+' if deltas['seo_delta'] > 0 else ''}{deltas['seo_delta']}")
            if deltas.get("traction_delta"):
                bits.append(f"{'+' if deltas['traction_delta'] > 0 else ''}{deltas['traction_delta']} mentions")
            summary = ("This run: " + ", ".join(bits) + ".") if bits else "No significant changes since the last run."

    version = store.create_version(
        project_id, run_id=run_id, kind=kind, snapshot=curr, summary_md=summary
    )
    log.info("version_created", project_id=project_id, version=version.get("version_num"), new_actions=new_actions)
    return version
