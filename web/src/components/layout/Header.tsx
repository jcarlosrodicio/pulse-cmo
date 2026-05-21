"use client";

import { useEffect, useRef, useState } from "react";
import {
  ExternalLink,
  Play,
  Loader2,
  Menu,
  ChevronDown,
  RotateCcw,
  Sparkles,
  Rocket,
  History,
} from "lucide-react";
import type { Project, AgentEvent } from "@/lib/api";
import { TerminalBar, type TerminalState } from "./TerminalBar";
import { PulseLogo } from "../ui/PulseLogo";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { ProfileMenu } from "./ProfileMenu";

export function Header({
  project,
  projects,
  onSwitchProject,
  onAddNewProject,
  isStreaming,
  events,
  terminalState,
  setTerminalState,
  hasFirstDive,
  onRun,
  onRedoFirstDive,
  onOpenProviderSettings,
  onOpenLaunch,
  onOpenVersions,
  onToggleMobileNav,
  runStatus,
  lastRunCostUsd,
  lastRunTokens,
  lastRunCalls,
}: {
  project: Project;
  projects: Project[];
  onSwitchProject: (p: Project) => void;
  onAddNewProject: () => void;
  isStreaming: boolean;
  events: AgentEvent[];
  terminalState: TerminalState;
  setTerminalState: (s: TerminalState) => void;
  hasFirstDive: boolean;
  onRun: () => void;
  onRedoFirstDive: () => void;
  onOpenProviderSettings: () => void;
  onOpenLaunch: () => void;
  onOpenVersions: () => void;
  onToggleMobileNav?: () => void;
  runStatus: "idle" | "running" | "done";
  lastRunCostUsd?: number | null;
  lastRunTokens?: number | null;
  lastRunCalls?: number | null;
}) {
  return (
    <header className="z-30" style={{ background: "var(--bg)", borderBottom: "1px solid var(--border)" }}>
      <div className="flex items-center gap-3 px-4 lg:px-5 py-2.5">
        {/* mobile menu */}
        <button
          onClick={onToggleMobileNav}
          className="lg:hidden p-2 rounded hover:bg-white/5 text-fg-dim"
          aria-label="menu"
        >
          <Menu size={16} />
        </button>

        {/* brand */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-accent">
            <PulseLogo size={18} />
          </span>
          <span className="font-mono text-[13px] tracking-tight font-medium">pulse</span>
        </div>

        {/* project switcher */}
        <ProjectSwitcher
          current={project}
          projects={projects}
          onSelect={onSwitchProject}
          onAddNew={onAddNewProject}
        />

        {/* status pill */}
        <div className="flex items-center gap-2 px-2.5 py-1 rounded border bg-surface"
             style={{ borderColor: "var(--border)" }}>
          <span className={runStatus === "running" ? "pulse-dot" : "pulse-dot dim"} />
          <span className="font-mono text-[11px] uppercase tracking-wider text-muted-strong">
            {runStatus === "running" ? "Running" : runStatus === "done" ? "Idle" : "Standby"}
          </span>
        </div>

        <div className="flex-1" />

        {/* launch mode */}
        <button
          onClick={onOpenLaunch}
          className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded border font-medium text-[12.5px] btn-press transition-colors text-muted-strong hover:text-fg"
          style={{ borderColor: "var(--border-strong)" }}
          title="Launch mode — archetype-driven GTM plan"
        >
          <Rocket size={13} />
          Launch
        </button>

        {/* run split-button */}
        <RunSplitButton
          isStreaming={isStreaming}
          hasFirstDive={hasFirstDive}
          onRun={onRun}
          onRedoFirstDive={onRedoFirstDive}
        />

        <button
          onClick={onOpenVersions}
          className="hidden md:flex p-1.5 rounded hover:bg-white/5 text-muted-strong"
          aria-label="version history"
          title="version history"
        >
          <History size={15} />
        </button>
        <a
          href={project.url}
          target="_blank"
          rel="noreferrer"
          className="hidden md:flex p-1.5 rounded hover:bg-white/5 text-muted-strong"
          aria-label="open site"
        >
          <ExternalLink size={14} />
        </a>
        <ProfileMenu
          costUsd={lastRunCostUsd ?? null}
          tokens={lastRunTokens ?? null}
          llmCalls={lastRunCalls ?? null}
          onOpenSettings={onOpenProviderSettings}
        />
      </div>

      {/* terminal sub-bar */}
      <div className="px-4 lg:px-5 pb-3">
        <TerminalBar
          events={events}
          isStreaming={isStreaming}
          state={terminalState}
          setState={setTerminalState}
        />
      </div>
    </header>
  );
}

function RunSplitButton({
  isStreaming,
  hasFirstDive,
  onRun,
  onRedoFirstDive,
}: {
  isStreaming: boolean;
  hasFirstDive: boolean;
  onRun: () => void;
  onRedoFirstDive: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onMouse(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onMouse);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouse);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const primaryLabel = hasFirstDive ? "Run now" : "First dive";

  return (
    <div ref={ref} className="relative flex items-stretch shrink-0">
      <button
        onClick={onRun}
        disabled={isStreaming}
        className="flex items-center gap-1.5 pl-3 pr-2.5 py-1.5 rounded-l border font-medium text-[12.5px] transition-colors disabled:opacity-50 disabled:cursor-not-allowed btn-press"
        style={{
          borderColor: "var(--accent)",
          background: "var(--accent-soft)",
          color: "var(--accent)",
        }}
      >
        {isStreaming ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} fill="currentColor" />}
        {primaryLabel}
      </button>
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={isStreaming}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="more run options"
        className="flex items-center justify-center px-1.5 py-1.5 rounded-r border border-l-0 transition-colors disabled:opacity-50 disabled:cursor-not-allowed btn-press"
        style={{
          borderColor: "var(--accent)",
          background: "var(--accent-soft)",
          color: "var(--accent)",
        }}
      >
        <ChevronDown size={12} />
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-1.5 w-[260px] rounded-xl border z-50"
          style={{
            background: "var(--surface)",
            borderColor: "var(--border-strong)",
            boxShadow: "0 8px 24px rgba(0,0,0,0.25)",
          }}
          role="menu"
        >
          <RunMenuItem
            icon={<Sparkles size={13} />}
            title="Run daily pass"
            subtitle="Incremental — 3-5 quick actions"
            shortcut="G"
            onClick={() => {
              setOpen(false);
              onRun();
            }}
            disabled={!hasFirstDive}
          />
          <div style={{ borderTop: "1px solid var(--border)" }} />
          <RunMenuItem
            icon={<RotateCcw size={13} />}
            title="Redo first dive"
            subtitle="Full re-scan: crawl, audit, drafts"
            onClick={() => {
              setOpen(false);
              if (
                window.confirm(
                  "Redo the full first dive? This re-runs the deep scan (crawl, audit, brand voice, drafts) and may overwrite generated documents.",
                )
              ) {
                onRedoFirstDive();
              }
            }}
            tone="warn"
          />
        </div>
      )}
    </div>
  );
}

function RunMenuItem({
  icon,
  title,
  subtitle,
  shortcut,
  onClick,
  disabled,
  tone,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  shortcut?: string;
  onClick: () => void;
  disabled?: boolean;
  tone?: "warn";
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      role="menuitem"
      className="w-full flex items-start gap-2.5 px-3.5 py-2.5 hover:bg-white/4 text-left btn-press disabled:opacity-40 disabled:cursor-not-allowed"
    >
      <span
        className="mt-0.5"
        style={{ color: tone === "warn" ? "var(--warn)" : "var(--accent)" }}
      >
        {icon}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px] font-medium leading-tight">{title}</div>
        <div className="text-[11px] text-muted mt-0.5">{subtitle}</div>
      </div>
      {shortcut && (
        <kbd className="font-mono text-[10.5px] text-muted bg-white/4 px-1.5 py-0.5 rounded mt-0.5">
          {shortcut}
        </kbd>
      )}
    </button>
  );
}
