"use client";

import { ExternalLink, Play, Loader2, Settings2, Menu } from "lucide-react";
import type { Project, AgentEvent } from "@/lib/api";
import { TerminalBar, type TerminalState } from "./TerminalBar";
import { PulseLogo } from "../ui/PulseLogo";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { ThemeToggle } from "../ui/Theme";

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
  onOpenSettings,
  onToggleMobileNav,
  runStatus,
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
  onOpenSettings: () => void;
  onToggleMobileNav?: () => void;
  runStatus: "idle" | "running" | "done";
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

        {/* run button */}
        <button
          onClick={onRun}
          disabled={isStreaming}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded border font-medium text-[12.5px] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            borderColor: "var(--accent)",
            background: "var(--accent-soft)",
            color: "var(--accent)",
          }}
        >
          {isStreaming ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} fill="currentColor" />}
          {hasFirstDive ? "Run now" : "First dive"}
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
        <ThemeToggle />
        <button
          onClick={onOpenSettings}
          className="p-1.5 rounded hover:bg-white/5 text-muted-strong"
          aria-label="settings"
        >
          <Settings2 size={15} />
        </button>
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
