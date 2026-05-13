"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AgentEvent, type RunSummary, type TargetKind } from "@/lib/api";

export function useRunStream(projectId: number) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const stopRef = useRef<(() => void) | null>(null);
  const onActionsChangedRef = useRef<() => void>(() => {});
  const onRunFinishedRef = useRef<(runId: number, status: string) => void>(() => {});

  const refreshRuns = useCallback(async () => {
    const list = await api.listRuns(projectId);
    setRuns(list);
    return list;
  }, [projectId]);

  // Whenever the projectId changes, reset state and pick the latest run.
  useEffect(() => {
    let cancelled = false;
    setActiveRunId(null);
    setRuns([]);
    setEvents([]);
    setIsStreaming(false);
    (async () => {
      const list = await api.listRuns(projectId);
      if (cancelled) return;
      setRuns(list);
      if (list.length > 0) setActiveRunId(list[0].id);
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // hydrate events on run change + open SSE if running, plus poll as a fallback
  useEffect(() => {
    if (!activeRunId) {
      setEvents([]);
      setIsStreaming(false);
      return;
    }
    let cancelled = false;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    setEvents([]);
    setIsStreaming(false);

    (async () => {
      try {
        const run = await api.getRun(activeRunId);
        if (cancelled) return;
        setEvents(run.log || []);
        if (run.status === "running") {
          setIsStreaming(true);
          stopRef.current?.();
          stopRef.current = api.streamRun(activeRunId, (ev) => {
            if (ev.type === "_done") {
              setIsStreaming(false);
              if (pollTimer) clearInterval(pollTimer);
              onActionsChangedRef.current?.();
              refreshRuns();
              onRunFinishedRef.current?.(activeRunId, ev.status || "done");
              return;
            }
            setEvents((prev) => [...prev, ev]);
            if (ev.type === "tool_result") onActionsChangedRef.current?.();
          });

          // safety-net polling — refetches the run every 3s, swaps in the
          // server-merged live log if SSE drops or never connected
          pollTimer = setInterval(async () => {
            try {
              const fresh = await api.getRun(activeRunId);
              if (cancelled) return;
              if (fresh.log && fresh.log.length > 0) {
                setEvents(fresh.log);
              }
              if (fresh.status !== "running") {
                setIsStreaming(false);
                if (pollTimer) clearInterval(pollTimer);
                onActionsChangedRef.current?.();
                refreshRuns();
                onRunFinishedRef.current?.(activeRunId, fresh.status);
              }
            } catch {
              // noop — try again next tick
            }
          }, 3000);
        }
      } catch {
        // noop
      }
    })();

    return () => {
      cancelled = true;
      stopRef.current?.();
      stopRef.current = null;
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [activeRunId, refreshRuns]);

  const onActionsChanged = useCallback((fn: () => void) => {
    onActionsChangedRef.current = fn;
  }, []);

  const onRunFinished = useCallback(
    (fn: (runId: number, status: string) => void) => {
      onRunFinishedRef.current = fn;
    },
    [],
  );

  const start = useCallback(
    async (
      kind: "first_dive" | "daily" | "manual" | "targeted" = "daily",
      extra?: { target?: TargetKind; topic?: string; instruction?: string },
    ) => {
      const r = await api.startRun(projectId, kind, extra?.instruction ?? "", {
        target: extra?.target,
        topic: extra?.topic,
      });
      await refreshRuns();
      setActiveRunId(r.run_id);
    },
    [projectId, refreshRuns],
  );

  return {
    runs,
    activeRunId,
    setActiveRunId,
    events,
    isStreaming,
    start,
    refreshRuns,
    onActionsChanged,
    onRunFinished,
  };
}
