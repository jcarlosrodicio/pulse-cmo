"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Compass,
  Loader2,
  CheckCircle2,
  Circle,
  Flag,
  TrendingUp,
  ChevronDown,
  ChevronRight,
  LineChart,
} from "lucide-react";
import { api, type GtmState } from "@/lib/api";

/**
 * The GTM loop — the product's spine, surfaced at the top of the main column.
 *
 *   The bet  ·  This week's 3 moves  ·  Log this week → the call
 *
 * This replaces the old "pile of generated posts": the moves ARE the week's
 * work, the bet is the one channel everything serves, and "Log this week" runs
 * the reality loop (numbers in → the call → next week's plan).
 */
export function GtmLoopPanel({
  projectId,
  isInitialDive,
  reloadKey,
  onLogWeek,
}: {
  projectId: number;
  isInitialDive: boolean;
  reloadKey: number;
  onLogWeek: (weekNum: number | null) => void;
}) {
  const [gtm, setGtm] = useState<GtmState | null>(null);
  const [loading, setLoading] = useState(true);
  const [showPlay, setShowPlay] = useState(false);

  const load = useCallback(async () => {
    try {
      const g = await api.getGtm(projectId);
      setGtm(g);
    } catch {
      setGtm(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setLoading(true);
    setShowPlay(false);
    load();
  }, [load, reloadKey]);

  const week = gtm?.current_week ?? null;
  const bet = gtm?.bet ?? null;
  // most recent reviewed week that isn't the open one — "last week's call"
  const lastCall = (gtm?.weeks ?? []).find((w) => w.review && w.id !== week?.id)?.review ?? null;
  const lastCallWeek = (gtm?.weeks ?? []).find((w) => w.review && w.id !== week?.id)?.week_num ?? null;

  const toggleMove = async (idx: number) => {
    if (!week?.plan) return;
    const cur = week.plan.moves[idx]?.done ?? false;
    // optimistic
    setGtm((g) =>
      g && g.current_week?.plan
        ? {
            ...g,
            current_week: {
              ...g.current_week,
              plan: {
                ...g.current_week.plan,
                moves: g.current_week.plan.moves.map((m, i) => (i === idx ? { ...m, done: !cur } : m)),
              },
            },
          }
        : g,
    );
    try {
      await api.setGtmMoveDone(projectId, week.id, idx, !cur);
    } catch {
      load(); // revert to server truth
    }
  };

  // --- empty / loading states ---------------------------------------------
  if (loading && !gtm) {
    return (
      <Frame>
        <div className="flex items-center gap-2 text-muted text-[12px] py-2">
          <Loader2 size={13} className="animate-spin text-accent" /> Loading your GTM plan…
        </div>
      </Frame>
    );
  }
  if (!bet) {
    return (
      <Frame>
        <div className="flex items-start gap-2.5 py-1">
          <Compass size={15} className="text-accent mt-0.5 shrink-0" />
          <div>
            <div className="text-[12.5px] font-medium text-fg">No channel bet yet</div>
            <div className="text-[11.5px] text-muted leading-relaxed mt-0.5">
              {isInitialDive
                ? "The first dive is committing your one channel bet and this week's moves…"
                : "Run a first dive — Pulse will pick the one channel to bet on and lay out week 1."}
            </div>
          </div>
        </div>
      </Frame>
    );
  }

  // --- the loop ------------------------------------------------------------
  const moves = week?.plan?.moves ?? [];
  const doneCount = moves.filter((m) => m.done).length;

  return (
    <Frame>
      <div className="space-y-3.5">
        {/* THE BET */}
        <div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.14em] text-muted font-semibold">
              <Compass size={11} className="text-accent" /> The bet
            </div>
            <button
              onClick={() => setShowPlay((v) => !v)}
              className="flex items-center gap-0.5 text-[10.5px] text-muted hover:text-fg btn-press"
            >
              {showPlay ? <ChevronDown size={12} /> : <ChevronRight size={12} />} the play
            </button>
          </div>
          <div className="text-[15px] font-semibold text-fg mt-1 leading-tight">{bet.channel}</div>
          <div className="flex items-start gap-1.5 text-[11.5px] text-fg-dim mt-1.5 leading-relaxed">
            <TrendingUp size={12} className="text-accent mt-0.5 shrink-0" />
            <span>
              <span className="text-muted">Working when: </span>
              {bet.leading_indicator}
            </span>
          </div>
          {showPlay && (
            <div
              className="mt-2 rounded-lg p-2.5 text-[11.5px] space-y-1.5"
              style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
            >
              <p className="text-fg-dim leading-relaxed">{bet.why_this_one}</p>
              <PlayRow label="Asset" value={bet.play.asset} />
              <PlayRow label="Cadence" value={bet.play.cadence} />
              <PlayRow label="Targets" value={bet.play.targets} />
              <div className="flex items-start gap-1.5 text-[11px] pt-0.5" style={{ color: "var(--danger)" }}>
                <Flag size={11} className="mt-0.5 shrink-0" />
                <span>
                  <span className="opacity-70">Kill if: </span>
                  {bet.kill_criteria}
                </span>
              </div>
            </div>
          )}
        </div>

        <div style={{ borderTop: "1px solid var(--border)" }} />

        {/* THIS WEEK */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.14em] text-muted font-semibold">
              This week{week ? ` · week ${week.week_num}` : ""}
              {moves.length > 0 && (
                <span className="text-muted/70 normal-case tracking-normal">
                  · {doneCount}/{moves.length} done
                </span>
              )}
            </div>
            <button
              onClick={() => onLogWeek(week?.week_num ?? null)}
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium btn-press"
              style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent-strong)" }}
            >
              <LineChart size={11} /> Log this week
            </button>
          </div>
          {week?.plan?.focus && (
            <p className="text-[11.5px] text-fg-dim leading-relaxed mb-2">{week.plan.focus}</p>
          )}
          <div className="space-y-1.5">
            {moves.map((m, i) => (
              <button
                key={i}
                onClick={() => toggleMove(i)}
                className="w-full flex items-start gap-2 text-left rounded-lg p-2 btn-press transition-colors"
                style={{
                  background: m.done ? "var(--surface)" : "transparent",
                  border: "1px solid var(--border)",
                }}
              >
                {m.done ? (
                  <CheckCircle2 size={15} className="text-accent mt-0.5 shrink-0" />
                ) : (
                  <Circle size={15} className="text-muted mt-0.5 shrink-0" />
                )}
                <span className="min-w-0">
                  <span
                    className="text-[12px] leading-snug block"
                    style={{ color: m.done ? "var(--muted)" : "var(--fg)", textDecoration: m.done ? "line-through" : "none" }}
                  >
                    {m.move}
                  </span>
                  {m.leading_indicator && (
                    <span className="text-[10.5px] text-muted block mt-0.5">→ {m.leading_indicator}</span>
                  )}
                </span>
              </button>
            ))}
            {moves.length === 0 && (
              <div className="text-[11.5px] text-muted py-1">No moves yet for this week.</div>
            )}
          </div>
        </div>

        {/* LAST WEEK'S CALL */}
        {lastCall && (
          <>
            <div style={{ borderTop: "1px solid var(--border)" }} />
            <div>
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.14em] text-muted font-semibold mb-1.5">
                Last week&apos;s call{lastCallWeek ? ` · week ${lastCallWeek}` : ""}
                <CallBadge kind={lastCall.call_kind} />
              </div>
              <p className="text-[11.5px] text-fg-dim leading-relaxed">{lastCall.the_call}</p>
            </div>
          </>
        )}
      </div>
    </Frame>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="p-4" style={{ borderBottom: "1px solid var(--border)", background: "var(--bg)" }}>
      {children}
    </div>
  );
}

function PlayRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-1.5">
      <span className="text-muted shrink-0 w-14">{label}</span>
      <span className="text-fg-dim leading-relaxed">{value}</span>
    </div>
  );
}

function CallBadge({ kind }: { kind: "continue" | "adjust" | "kill" }) {
  const map = {
    continue: { c: "var(--accent)", bg: "var(--accent-soft)", b: "var(--accent-strong)" },
    adjust: { c: "#b8860b", bg: "rgba(212,160,23,0.12)", b: "rgba(212,160,23,0.4)" },
    kill: { c: "var(--danger)", bg: "rgba(220,80,80,0.12)", b: "rgba(220,80,80,0.4)" },
  }[kind] || { c: "var(--muted)", bg: "var(--surface)", b: "var(--border)" };
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[9.5px] font-semibold uppercase tracking-wider normal-case"
      style={{ color: map.c, background: map.bg, border: `1px solid ${map.b}` }}
    >
      {kind}
    </span>
  );
}
