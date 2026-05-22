"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  api,
  type Action,
  type AgentEvent,
  type DocumentKind,
  type Project,
  type TargetKind,
  type WritingInstructions,
} from "@/lib/api";
import { DocumentSheet } from "@/components/company/DocumentSheet";
import { Onboarding } from "@/components/Onboarding";
import { AddProjectModal } from "@/components/AddProjectModal";
import { Header } from "@/components/layout/Header";
import { Shell } from "@/components/layout/Shell";
import { CompanySidebar } from "@/components/company/CompanySidebar";
import { AnalyticsPanel } from "@/components/analytics/AnalyticsPanel";
import { ActionsFeed } from "@/components/actions/ActionsFeed";
import { ActionDetailSheet } from "@/components/actions/ActionDetailSheet";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { WritingInstructionsModal } from "@/components/settings/WritingInstructions";
import { SettingsSheet } from "@/components/settings/SettingsSheet";
import { LaunchWorkspace } from "@/components/launch/LaunchWorkspace";
import { VersionsSheet } from "@/components/versions/VersionsSheet";
import { KeyboardShortcuts } from "@/components/ui/KeyboardShortcuts";
import { useToast } from "@/components/ui/Toast";
import { useRunStream } from "@/hooks/useRunStream";

import { metaFor } from "@/lib/actionTypes";
const ACTIVE_PROJECT_KEY = "pulse:activeProjectId";

function actionTypeLabel(t: Action["action_type"]): string {
  return metaFor(t).label;
}

function nextRunIso(
  project: Project,
  runs: { status: string }[],
): string | null {
  if (runs.some((r) => r.status === "running")) return null;
  const now = new Date();
  const next = new Date(now);
  next.setHours(project.schedule_hour, project.schedule_minute, 0, 0);
  if (next.getTime() <= now.getTime()) {
    next.setDate(next.getDate() + 1);
  }
  return next.toISOString();
}

export default function Page() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);

  const refreshProjects = useCallback(
    async (selectNewId?: number) => {
      const list = await api.listProjects();
      setProjects(list);
      if (selectNewId !== undefined) {
        setActiveId(selectNewId);
      } else if (activeId === null && list.length > 0) {
        const stored = typeof window !== "undefined" ? Number(localStorage.getItem(ACTIVE_PROJECT_KEY)) : 0;
        const exists = list.find((p) => p.id === stored);
        setActiveId(exists ? exists.id : list[0].id);
      }
      return list;
    },
    [activeId],
  );

  useEffect(() => {
    (async () => {
      try {
        await api.health();
        await refreshProjects();
      } catch (e) {
        setError(String((e as Error).message || e));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeId !== null && typeof window !== "undefined") {
      localStorage.setItem(ACTIVE_PROJECT_KEY, String(activeId));
    }
  }, [activeId]);

  async function handleCreate(url: string) {
    const p = await api.createProject({ url, start_dive: true });
    await refreshProjects(p.id);
    setShowAddModal(false);
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="max-w-md text-center">
          <div className="text-danger mb-2">backend unreachable</div>
          <div className="text-muted text-[11.5px] font-mono">{error}</div>
          <div className="text-muted text-[11.5px] mt-3">
            run <code className="px-1.5 py-0.5 rounded bg-white/5 font-mono">uv run pulse</code> from the project root.
          </div>
        </div>
      </div>
    );
  }

  if (projects === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 size={20} className="animate-spin text-accent" />
      </div>
    );
  }

  if (projects.length === 0) {
    return <Onboarding onCreate={handleCreate} />;
  }

  const active = projects.find((p) => p.id === activeId) ?? projects[0];

  return (
    <>
      <Dashboard
        project={active}
        projects={projects}
        onSwitchProject={(p) => setActiveId(p.id)}
        onAddNewProject={() => setShowAddModal(true)}
        onProjectsRefresh={refreshProjects}
      />
      <AddProjectModal
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        onCreate={handleCreate}
      />
    </>
  );
}

function Dashboard({
  project,
  projects,
  onSwitchProject,
  onAddNewProject,
  onProjectsRefresh,
}: {
  project: Project;
  projects: Project[];
  onSwitchProject: (p: Project) => void;
  onAddNewProject: () => void;
  onProjectsRefresh: (selectId?: number) => Promise<Project[]>;
}) {
  const [actions, setActions] = useState<Action[]>([]);
  const [selectedAction, setSelectedAction] = useState<Action | null>(null);
  const [selectedDocKind, setSelectedDocKind] = useState<DocumentKind | null>(null);
  const [syntheticLog, setSyntheticLog] = useState<AgentEvent[]>([]);
  const logConsole = useCallback(
    (kind: "tool" | "result" | "meta" | "text" | "error" | "thought" | "user", text: string) => {
      setSyntheticLog((prev) =>
        [
          ...prev,
          ({ _synthetic: true, kind, text } as unknown) as AgentEvent,
        ].slice(-40),
      );
    },
    [],
  );
  const [terminalState, setTerminalState] = useState<"collapsed" | "default" | "expanded">(() => {
    if (typeof window === "undefined") return "default";
    const stored = localStorage.getItem("pulse:terminalState");
    if (stored === "collapsed" || stored === "default" || stored === "expanded") return stored;
    return "default";
  });
  useEffect(() => {
    if (typeof window !== "undefined")
      localStorage.setItem("pulse:terminalState", terminalState);
  }, [terminalState]);
  const [showWritingModal, setShowWritingModal] = useState(false);
  const [showProviderSettings, setShowProviderSettings] = useState(false);
  const [showLaunch, setShowLaunch] = useState(false);
  const [showVersions, setShowVersions] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [generatingTarget, setGeneratingTarget] = useState<TargetKind | null>(null);
  const [mobilePane, setMobilePane] = useState<"company" | "analytics" | "actions" | "chat">("actions");
  const toast = useToast();
  const knownActionIdsRef = useRef<Set<number>>(new Set());

  const refreshActions = useCallback(async () => {
    const list = await api.listActions(project.id);
    // Toast on newly-arrived actions (skip the very first refresh of a project)
    if (knownActionIdsRef.current.size > 0) {
      const fresh = list.filter((a) => !knownActionIdsRef.current.has(a.id));
      if (fresh.length === 1) {
        const a = fresh[0];
        toast.push({
          kind: "success",
          title: actionTypeLabel(a.action_type) + " drafted",
          detail: a.title,
          action: { label: "Open", onClick: () => setSelectedAction(a) },
        });
      } else if (fresh.length > 1) {
        toast.push({
          kind: "success",
          title: `${fresh.length} new actions`,
          detail: "open the feed to review",
        });
      }
    }
    knownActionIdsRef.current = new Set(list.map((a) => a.id));
    setActions(list);
  }, [project.id, toast]);

  const refreshActiveProject = useCallback(async () => {
    const p = await api.getProject(project.id);
    onProjectsRefresh(p.id);
  }, [project.id, onProjectsRefresh]);

  const { events, isStreaming, runs, start, onActionsChanged, onRunFinished } = useRunStream(project.id);

  useEffect(() => {
    onActionsChanged(() => {
      refreshActions();
      refreshActiveProject();
    });
  }, [onActionsChanged, refreshActions, refreshActiveProject]);

  useEffect(() => {
    onRunFinished((_runId, status) => {
      if (status === "done") {
        toast.push({
          kind: "success",
          title: "Run complete",
          detail: "New actions are in the feed",
        });
      } else if (status === "failed") {
        toast.push({
          kind: "error",
          title: "Run failed",
          detail: "Check the terminal log for details",
        });
      }
    });
  }, [onRunFinished, toast]);

  useEffect(() => {
    refreshActions();
  }, [refreshActions]);

  // poll actions + project while a run is in flight — SSE may not deliver
  // every tool_result on a slow connection, so this is a safety net
  useEffect(() => {
    if (!project.active_run_id) return;
    const id = setInterval(() => {
      refreshActions();
      refreshActiveProject();
    }, 4000);
    return () => clearInterval(id);
  }, [project.active_run_id, refreshActions, refreshActiveProject]);

  // "First dive" is considered done once any first_dive run has reached a
  // terminal state (done OR failed). A failed first dive shouldn't trap the
  // CTA forever — the user can always re-run it via "Run now".
  const hasFirstDive = runs.some(
    (r) => r.kind === "first_dive" && r.status !== "running",
  );
  const runStatus: "idle" | "running" | "done" = isStreaming ? "running" : hasFirstDive ? "done" : "idle";
  // a first dive is "initial" when there's no completed dive yet (whether it's
  // running right now or hasn't been kicked off yet, the panels are empty so
  // show skeletons)
  const isInitialDive = !hasFirstDive && (isStreaming || runs.length === 0);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      const inField =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;
      if (e.key === "Escape") {
        setSelectedAction(null);
        setShowShortcuts(false);
        return;
      }
      if (inField) return;
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setMobilePane("chat");
        return;
      }
      if (e.key === "n" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onAddNewProject();
        return;
      }
      if (e.key === "?" || (e.shiftKey && e.key === "/")) {
        e.preventDefault();
        setShowShortcuts((v) => !v);
        return;
      }
      if (e.key === "g" || e.key === "G") {
        if (!isStreaming) start(hasFirstDive ? "daily" : "first_dive");
        return;
      }
      if (e.key === "r" || e.key === "R") {
        refreshActions();
        return;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isStreaming, hasFirstDive, start, onAddNewProject, refreshActions]);

  const setActionStatus = async (a: Action, status: Action["status"]) => {
    const updated = await api.updateAction(a.id, { status });
    setActions((prev) => prev.map((p) => (p.id === a.id ? updated : p)));
    if (selectedAction?.id === a.id) setSelectedAction(updated);
    logConsole("meta", `action #${a.id} → ${status}`);
  };

  const setActionContent = async (a: Action, content: string, title?: string) => {
    const updated = await api.updateAction(a.id, { content, title });
    setActions((prev) => prev.map((p) => (p.id === a.id ? updated : p)));
    setSelectedAction(updated);
    logConsole("meta", `action #${a.id} edited`);
  };

  const saveWritingInstructions = async (wi: WritingInstructions) => {
    logConsole("tool", "saving writing instructions…");
    await api.updateProject(project.id, { writing_instructions: wi });
    refreshActiveProject();
    logConsole("result", "✓ writing instructions saved");
  };

  const saveSchedule = async (times: string[]) => {
    await api.updateProject(project.id, { schedule_times: times });
    refreshActiveProject();
    logConsole("result", `✓ schedule updated · ${times.join(", ")}`);
  };

  // when isStreaming flips back to false, clear the generating flag.
  useEffect(() => {
    if (!isStreaming) setGeneratingTarget(null);
  }, [isStreaming]);

  const handleGenerate = useCallback(
    async (target: TargetKind, topic: string) => {
      setGeneratingTarget(target);
      const niceLabel = target.replace(/_/g, " ");
      logConsole("tool", `Pulse is generating ${niceLabel}${topic ? ` — ${topic}` : ""}…`);
      toast.push({
        kind: "info",
        title: `Generating ${niceLabel}`,
        detail: topic || "running focused pipeline",
      });
      try {
        await start("targeted", { target, topic });
      } catch (e) {
        setGeneratingTarget(null);
        toast.push({
          kind: "error",
          title: "Couldn't start run",
          detail: String((e as Error).message),
        });
      }
    },
    [start, toast, logConsole],
  );

  const saveProjectFromSidebar = async (patch: Partial<Project>) => {
    logConsole("tool", "Pulse is saving your company info…");
    await api.updateProject(project.id, patch);
    await refreshActiveProject();
    logConsole("result", "✓ Your company has been updated!");
    toast.push({
      kind: "success",
      title: "Company saved",
      detail: "Your project details have been updated.",
    });
  };

  const lastDoneRun = runs.find((r) => r.status === "done");
  const lastRunCostUsd = lastDoneRun?.cost_usd ?? null;
  const lastRunTokens = lastDoneRun?.total_tokens ?? null;

  const header = useMemo(
    () => (
      <Header
        project={project}
        projects={projects}
        onSwitchProject={onSwitchProject}
        onAddNewProject={onAddNewProject}
        isStreaming={isStreaming}
        events={[...events, ...syntheticLog]}
        terminalState={terminalState}
        setTerminalState={setTerminalState}
        hasFirstDive={hasFirstDive}
        onRun={() => start(hasFirstDive ? "daily" : "first_dive")}
        onRedoFirstDive={() => {
          logConsole("meta", "redoing first dive — full re-scan");
          toast.push({
            kind: "info",
            title: "Redoing first dive",
            detail: "Pulse is re-running the full deep scan.",
          });
          start("first_dive");
        }}
        onOpenProviderSettings={() => setShowProviderSettings(true)}
        onOpenLaunch={() => setShowLaunch(true)}
        onOpenVersions={() => setShowVersions(true)}
        onToggleMobileNav={() => setMobilePane("company")}
        runStatus={runStatus}
        lastRunCostUsd={lastRunCostUsd}
        lastRunTokens={lastRunTokens}
      />
    ),
    [project, projects, onSwitchProject, onAddNewProject, isStreaming, events, syntheticLog, terminalState, hasFirstDive, start, runStatus, lastRunCostUsd, lastRunTokens],
  );

  return (
    <>
      <Shell
        header={header}
        sidebar={
          <CompanySidebar
            project={project}
            actions={actions}
            onOpenAction={setSelectedAction}
            onOpenDocument={(kind) => {
              setSelectedDocKind(kind);
              logConsole("meta", `opening document: ${kind.replace(/_/g, " ")}`);
            }}
            onSaveProject={saveProjectFromSidebar}
            onEditSchedule={() => setShowWritingModal(true)}
            isInitialDive={isInitialDive}
          />
        }
        analytics={<AnalyticsPanel project={project} isInitialDive={isInitialDive} />}
        actions={
          <ActionsFeed
            actions={actions}
            onSelect={setSelectedAction}
            onRefresh={refreshActions}
            onOpenInstructions={() => setShowWritingModal(true)}
            onStatusChange={setActionStatus}
            onGenerate={handleGenerate}
            generatingTarget={generatingTarget}
            isInitialDive={isInitialDive}
            lastRunAt={lastDoneRun?.finished_at ?? null}
            nextRunAt={nextRunIso(project, runs)}
            runStatus={runStatus}
          />
        }
        chat={<ChatPanel projectId={project.id} />}
        mobilePane={mobilePane}
        setMobilePane={setMobilePane}
      />

      <ActionDetailSheet
        action={selectedAction}
        onClose={() => setSelectedAction(null)}
        onStatusChange={setActionStatus}
        onContentChange={setActionContent}
      />

      <DocumentSheet
        projectId={project.id}
        kind={selectedDocKind}
        onClose={() => setSelectedDocKind(null)}
        onLogConsole={logConsole}
      />

      <WritingInstructionsModal
        open={showWritingModal}
        onClose={() => setShowWritingModal(false)}
        project={project}
        onSave={saveWritingInstructions}
        onSaveSchedule={saveSchedule}
      />

      <SettingsSheet
        open={showProviderSettings}
        onClose={() => setShowProviderSettings(false)}
      />

      <LaunchWorkspace
        projectId={project.id}
        projectName={project.name}
        open={showLaunch}
        onClose={() => {
          setShowLaunch(false);
          refreshActions();
        }}
      />

      <VersionsSheet
        projectId={project.id}
        open={showVersions}
        onClose={() => setShowVersions(false)}
      />

      <KeyboardShortcuts open={showShortcuts} onClose={() => setShowShortcuts(false)} />
    </>
  );
}
