"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Plus, Check, Loader2, Globe } from "lucide-react";
import type { Project } from "@/lib/api";

export function ProjectSwitcher({
  current,
  projects,
  onSelect,
  onAddNew,
}: {
  current: Project;
  projects: Project[];
  onSelect: (p: Project) => void;
  onAddNew: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const host = current.url.replace(/^https?:\/\//, "").replace(/\/$/, "");

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded border bg-surface card-hover btn-press"
        style={{ borderColor: "var(--border-strong)" }}
      >
        <StatusDot project={current} />
        <span className="font-mono text-[12px] truncate max-w-[180px]">{host}</span>
        <ChevronDown
          size={12}
          className={`text-muted transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1.5 w-[320px] rounded-lg border bg-surface shadow-xl z-50 modal-card"
          style={{ borderColor: "var(--border-strong)" }}
        >
          <div
            className="px-3 py-2 text-[10.5px] uppercase tracking-[0.14em] text-muted font-medium flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <span>Projects · {projects.length}</span>
            {projects.some((p) => p.active_run_id) && (
              <span className="text-accent normal-case tracking-normal flex items-center gap-1">
                <Loader2 size={9} className="animate-spin" />
                running
              </span>
            )}
          </div>
          <ul className="max-h-[360px] overflow-y-auto p-1">
            {projects.map((p) => (
              <ProjectRow
                key={p.id}
                project={p}
                isActive={p.id === current.id}
                onClick={() => {
                  onSelect(p);
                  setOpen(false);
                }}
              />
            ))}
          </ul>
          <div className="p-1" style={{ borderTop: "1px solid var(--border)" }}>
            <button
              onClick={() => {
                onAddNew();
                setOpen(false);
              }}
              className="w-full flex items-center gap-2 px-2.5 py-2 rounded-md hover:bg-white/4 text-accent btn-press"
            >
              <Plus size={13} />
              <span className="text-[13px] font-medium">Add new project</span>
              <span className="ml-auto text-[10.5px] text-muted font-mono">⌘N</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ProjectRow({
  project,
  isActive,
  onClick,
}: {
  project: Project;
  isActive: boolean;
  onClick: () => void;
}) {
  const pending = useMemo(() => {
    const counts = project.action_counts || {};
    return Object.values(counts).reduce((a, b) => a + b, 0);
  }, [project.action_counts]);
  const lastRunRel = useMemo(() => {
    const ts = project.latest_run?.finished_at;
    if (!ts) return null;
    return relTime(new Date(ts));
  }, [project.latest_run]);

  return (
    <li>
      <button
        onClick={onClick}
        className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-left transition-colors btn-press ${
          isActive ? "bg-white/8" : "hover:bg-white/4"
        }`}
      >
        <StatusDot project={project} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <div className="text-[13px] font-medium truncate">{project.name}</div>
            {pending > 0 && (
              <span
                className="count-badge"
                style={{
                  background: "var(--accent-soft)",
                  color: "var(--accent)",
                }}
              >
                {pending}
              </span>
            )}
          </div>
          <div className="text-[11px] text-muted font-mono truncate">
            {project.url.replace(/^https?:\/\//, "")}
            {lastRunRel && (
              <span className="opacity-70"> · last run {lastRunRel}</span>
            )}
            {project.active_run_id && (
              <span className="text-accent ml-1.5">· running</span>
            )}
          </div>
        </div>
        {isActive && <Check size={12} className="text-accent shrink-0" />}
      </button>
    </li>
  );
}

function StatusDot({ project }: { project: Project }) {
  if (project.active_run_id) {
    return <Loader2 size={11} className="animate-spin text-accent shrink-0" />;
  }
  if (project.latest_run?.status === "done") {
    return <span className="pulse-dot dim shrink-0" />;
  }
  return <Globe size={11} className="text-muted shrink-0" />;
}

function relTime(d: Date): string {
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
