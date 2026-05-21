"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  X,
  Rocket,
  Loader2,
  Sparkles,
  Check,
  ChevronRight,
  ChevronDown,
  Target,
  AlertTriangle,
  RefreshCw,
  Wand2,
  Trash2,
  Copy,
  ExternalLink,
  Pencil,
} from "lucide-react";
import {
  api,
  type LaunchCampaign,
  type LaunchPlan,
  type LaunchArchetypeKey,
  type LaunchIntake,
  type LaunchDay,
  type LaunchAdvice,
  type LaunchClassification,
  type LaunchContentPiece,
  type LaunchContentKind,
} from "@/lib/api";
import { useToast } from "../ui/Toast";

const ARCHETYPE_LABELS: Record<LaunchArchetypeKey, string> = {
  viral_artifact: "Viral artifact / generator",
  dev_tool: "Dev tool / API / library",
  b2b_saas: "B2B SaaS",
  consumer: "Consumer app",
  open_source: "Open source",
  marketplace: "Marketplace / network",
};

const CONTENT_LABEL: Record<LaunchContentKind, string> = {
  tweet: "X / Tweet",
  reddit_post: "Reddit post",
  hn_post: "Show HN",
  linkedin: "LinkedIn",
  article: "Article",
};

// where to go to post each kind
const CONTENT_OPEN: Record<LaunchContentKind, { label: string; url: string }> = {
  tweet: { label: "Open X", url: "https://x.com/compose/post" },
  reddit_post: { label: "Open Reddit", url: "https://www.reddit.com/submit" },
  hn_post: { label: "Open HN", url: "https://news.ycombinator.com/submit" },
  linkedin: { label: "Open LinkedIn", url: "https://www.linkedin.com/feed/?shareActive=true" },
  article: { label: "—", url: "" },
};

export function LaunchWorkspace({
  projectId,
  projectName,
  open,
  onClose,
}: {
  projectId: number;
  projectName: string;
  open: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [campaign, setCampaign] = useState<LaunchCampaign | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { campaign } = await api.getLaunch(projectId);
      setCampaign(campaign);
    } catch {
      setCampaign(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  const start = async () => {
    setBusy("start");
    try {
      const { campaign } = await api.startLaunch(projectId);
      setCampaign(campaign);
      toast.push({ kind: "success", title: "Classified", detail: "Confirm the archetype below." });
    } catch (e) {
      toast.push({ kind: "error", title: "Couldn't start", detail: String((e as Error).message) });
    } finally {
      setBusy(null);
    }
  };

  const generatePlan = async (archetype: LaunchArchetypeKey) => {
    setBusy("plan");
    try {
      const { campaign } = await api.generateLaunchPlan(projectId, archetype);
      setCampaign(campaign);
      toast.push({ kind: "success", title: "Launch plan ready", detail: "Your Week-1 board is below." });
    } catch (e) {
      toast.push({ kind: "error", title: "Plan failed", detail: String((e as Error).message) });
    } finally {
      setBusy(null);
    }
  };

  const reset = async () => {
    if (!window.confirm("Discard this launch campaign and start over?")) return;
    await api.deleteLaunch(projectId);
    setCampaign(null);
  };

  if (!open) return null;

  const state = campaign?.state ?? null;

  return (
    <>
      <div className="sheet-overlay" onClick={onClose} />
      <div className="launch-panel">
        <header
          className="flex items-center gap-3 px-6 py-3.5 shrink-0"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--bg)" }}
        >
          <span className="text-accent"><Rocket size={17} /></span>
          <h2 className="text-[15px] font-semibold tracking-tight">Launch mode</h2>
          {campaign?.archetype && (
            <span
              className="text-[10.5px] uppercase tracking-[0.12em] font-medium font-mono px-2 py-0.5 rounded"
              style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent-strong)" }}
            >
              {ARCHETYPE_LABELS[campaign.archetype]}
            </span>
          )}
          <div className="flex-1" />
          {campaign && (
            <button onClick={reset} className="flex items-center gap-1 text-[11.5px] text-muted hover:text-danger btn-press px-2 py-1 rounded" title="discard">
              <Trash2 size={11} /> Reset
            </button>
          )}
          <button onClick={onClose} className="p-1.5 rounded hover:bg-white/5 text-muted" aria-label="close">
            <X size={16} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 size={20} className="animate-spin text-accent" />
            </div>
          ) : !campaign ? (
            <LaunchIntro onStart={start} busy={busy === "start"} projectName={projectName} />
          ) : (state === "intake" || state === "classify") && campaign.classification ? (
            <ConfirmView
              projectId={projectId}
              campaign={campaign}
              busy={busy}
              onIntake={(intake) => api.updateLaunch(projectId, { intake }).then((r) => setCampaign(r.campaign))}
              onGeneratePlan={generatePlan}
            />
          ) : campaign.plan ? (
            <TrackBoard projectId={projectId} campaign={campaign} onCampaign={setCampaign} />
          ) : (
            <LaunchIntro onStart={start} busy={busy === "start"} projectName={projectName} />
          )}
        </div>
      </div>
    </>
  );
}

/* ── intro ─────────────────────────────────────────────────────────── */

function LaunchIntro({ onStart, busy, projectName }: { onStart: () => void; busy: boolean; projectName: string }) {
  return (
    <div className="max-w-[560px] mx-auto px-6 py-14 text-center">
      <div className="w-12 h-12 rounded-2xl mx-auto mb-4 flex items-center justify-center" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
        <Rocket size={20} />
      </div>
      <h1 className="text-[22px] font-semibold tracking-tight mb-2">Plan {projectName}&rsquo;s launch</h1>
      <p className="text-[13.5px] text-muted leading-relaxed mb-6">
        Pulse reads everything it already knows about your product, classifies it
        into one growth archetype, and builds a day-by-day Week-1 plan, with the
        actual posts to write each day. You confirm; you don&rsquo;t fill out a form.
      </p>
      <button
        onClick={onStart}
        disabled={busy}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-[13px] btn-press disabled:opacity-50"
        style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
        {busy ? "Reading your product…" : "Plan my launch"}
      </button>
    </div>
  );
}

/* ── confirm (classification-first) ────────────────────────────────── */

function ConfirmView({
  projectId,
  campaign,
  busy,
  onIntake,
  onGeneratePlan,
}: {
  projectId: number;
  campaign: LaunchCampaign;
  busy: string | null;
  onIntake: (intake: LaunchIntake) => Promise<unknown>;
  onGeneratePlan: (a: LaunchArchetypeKey) => void;
}) {
  void projectId;
  const cls = campaign.classification as LaunchClassification;
  const [override, setOverride] = useState<LaunchArchetypeKey | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [intake, setIntake] = useState<LaunchIntake>(campaign.intake || {});
  const chosen = override ?? cls.archetype;

  const set = <K extends keyof LaunchIntake>(k: K, v: LaunchIntake[K]) => setIntake((p) => ({ ...p, [k]: v }));

  return (
    <div className="max-w-[640px] mx-auto px-6 py-8 space-y-5">
      <div className="text-center">
        <div className="text-[10.5px] uppercase tracking-[0.16em] text-muted font-medium mb-1">Pulse&rsquo;s read</div>
        <h1 className="text-[20px] font-semibold tracking-tight">This looks like a</h1>
      </div>

      {/* archetype card */}
      <div className="rounded-xl border bg-surface p-4" style={{ borderColor: "var(--accent-strong)" }}>
        <div className="flex items-center gap-2 mb-2">
          <Target size={14} className="text-accent" />
          <span className="text-[15px] font-semibold">{cls.facts?.label || ARCHETYPE_LABELS[cls.archetype]}</span>
          <span className="text-[10.5px] uppercase tracking-wider font-mono text-muted ml-auto">{cls.confidence} confidence</span>
        </div>
        <p className="text-[12.5px] text-fg-dim leading-relaxed mb-3">{cls.reasoning}</p>
        {cls.facts && (
          <div className="grid grid-cols-2 gap-3 text-[12px]">
            <DerivedFact label="North-star" value={cls.facts.north_star} />
            <DerivedFact label="Loop metric" value={cls.facts.loop_metric} />
            <DerivedFact label="Growth engine" value={cls.facts.growth_engine} span />
          </div>
        )}
        {cls.facts?.avoid && cls.facts.avoid.length > 0 && (
          <div className="flex items-start gap-1.5 text-[11.5px] text-muted mt-3">
            <AlertTriangle size={12} className="text-warn mt-0.5 shrink-0" />
            <span>Avoid: {cls.facts.avoid.join(", ")}</span>
          </div>
        )}
      </div>

      {/* override */}
      <div className="flex items-center gap-2">
        <span className="text-[11.5px] text-muted">Not right?</span>
        <select className="li-input flex-1" value={chosen} onChange={(e) => setOverride(e.target.value as LaunchArchetypeKey)}>
          {Object.entries(ARCHETYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>

      {/* inferred details (collapsed) */}
      <div className="rounded-xl border bg-surface overflow-hidden" style={{ borderColor: "var(--border)" }}>
        <button onClick={() => setShowDetails((v) => !v)} className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left btn-press">
          <Pencil size={12} className="text-muted" />
          <span className="text-[12.5px] font-medium flex-1">What Pulse inferred</span>
          <span className="text-[11px] text-muted">{showDetails ? "hide" : "review / edit"}</span>
          <ChevronDown size={14} className="text-muted transition-transform" style={{ transform: showDetails ? "rotate(0)" : "rotate(-90deg)" }} />
        </button>
        {showDetails && (
          <div className="px-3.5 pb-3.5 space-y-3" style={{ borderTop: "1px solid var(--border)" }}>
            <div className="grid grid-cols-2 gap-3 pt-3">
              <Field label="Pricing">
                <select className="li-input" value={intake.pricing || ""} onChange={(e) => set("pricing", e.target.value)}>
                  <option value="">unknown</option>
                  {["free", "freemium", "one-time", "subscription", "usage-based"].map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </Field>
              <Field label="Founder reach">
                <select className="li-input" value={intake.founder_reach || ""} onChange={(e) => set("founder_reach", e.target.value)}>
                  <option value="">unknown</option>
                  {["low", "mid", "high"].map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Audience"><input className="li-input" value={intake.audience_who || ""} onChange={(e) => set("audience_who", e.target.value)} /></Field>
            <Field label="Primary artifact"><input className="li-input" value={intake.primary_artifact || ""} onChange={(e) => set("primary_artifact", e.target.value)} placeholder="(none)" /></Field>
            <div className="grid grid-cols-2 gap-3">
              <ToggleField label="Retention loop?" value={intake.has_retention_loop} onChange={(v) => set("has_retention_loop", v)} />
              <ToggleField label="OG link unfurls?" value={intake.og_unfurl_works} onChange={(v) => set("og_unfurl_works", v)} />
            </div>
            <Field label="Launch date"><input type="date" className="li-input" value={intake.launch_date || ""} onChange={(e) => set("launch_date", e.target.value)} /></Field>
            <button
              onClick={() => onIntake(intake)}
              className="text-[11.5px] text-accent hover:opacity-80 btn-press"
            >
              Save details
            </button>
          </div>
        )}
      </div>

      <button
        onClick={() => onGeneratePlan(chosen)}
        disabled={busy === "plan"}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-medium text-[13px] btn-press disabled:opacity-50"
        style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
      >
        {busy === "plan" ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
        {busy === "plan" ? "Building your Week-1 plan…" : "Generate my Week-1 plan"}
      </button>
    </div>
  );
}

/* ── tracker board ─────────────────────────────────────────────────── */

function TrackBoard({
  projectId,
  campaign,
  onCampaign,
}: {
  projectId: number;
  campaign: LaunchCampaign;
  onCampaign: (c: LaunchCampaign) => void;
}) {
  const toast = useToast();
  const [plan, setPlan] = useState<LaunchPlan>(campaign.plan!);
  const [advice, setAdvice] = useState<LaunchAdvice | null>(null);
  const [adviceBusy, setAdviceBusy] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dayRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => { setPlan(campaign.plan!); }, [campaign.plan]);

  const persist = useCallback((next: LaunchPlan) => {
    setPlan(next);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      api.updateLaunch(projectId, { plan: next }).then((r) => onCampaign(r.campaign)).catch(() => {});
    }, 700);
  }, [projectId, onCampaign]);

  const score = useMemo(() => computeScore(plan), [plan]);
  const m = plan.metrics;

  const mutateDay = (di: number, fn: (d: LaunchDay) => LaunchDay) =>
    persist({ ...plan, days: plan.days.map((d, i) => (i === di ? fn(d) : d)) });

  const getMove = async () => {
    setAdviceBusy(true);
    try {
      await api.updateLaunch(projectId, { plan });
      setAdvice(await api.trackLaunch(projectId));
    } catch (e) {
      toast.push({ kind: "error", title: "Couldn't get advice", detail: String((e as Error).message) });
    } finally {
      setAdviceBusy(false);
    }
  };

  const draftPiece = async (di: number, pi: number) => {
    try {
      const { piece } = await api.draftLaunchContent(projectId, di, pi);
      // merge the drafted piece back into local plan
      setPlan((prev) => ({
        ...prev,
        days: prev.days.map((d, i) =>
          i === di ? { ...d, content_pieces: d.content_pieces.map((p, j) => (j === pi ? piece : p)) } : d,
        ),
      }));
      toast.push({ kind: "success", title: "Draft ready", detail: "Also saved to your Actions feed." });
    } catch (e) {
      toast.push({ kind: "error", title: "Draft failed", detail: String((e as Error).message) });
    }
  };

  const setPieceVariant = (di: number, pi: number, vi: number) =>
    mutateDay(di, (d) => ({
      ...d,
      content_pieces: d.content_pieces.map((p, j) => (j === pi ? { ...p, chosen_variant: vi } : p)),
    }));

  return (
    <div className="max-w-[900px] mx-auto px-6 py-6">
      {/* summary */}
      <div className="flex flex-wrap items-end gap-6 mb-4">
        <Stat big value={String(score.total_north)} label={`total ${m.north}`} />
        <Stat big value={score.k.toFixed(2)} label={`K (${m.loop}÷${m.north})`} tone={score.k >= 1 ? "good" : score.k > 0 ? "warn" : undefined} />
        <Stat big value={`${score.funnel_pct.toFixed(1)}%`} label="funnel" />
        <Stat big value={`${score.tasks_pct}%`} label={`${score.tasks_done}/${score.tasks_total} tasks`} />
        <div className="flex-1" />
        <div>
          <div className="text-[9.5px] uppercase tracking-[0.1em] text-muted mb-1">launch date</div>
          <input
            type="date"
            className="li-input w-[150px]"
            value={campaign.start_date || ""}
            onChange={(e) => api.updateLaunch(projectId, { start_date: e.target.value }).then((r) => onCampaign(r.campaign))}
          />
        </div>
      </div>

      {/* calendar strip */}
      <div className="flex gap-1.5 mb-5 overflow-x-auto pb-1">
        {plan.days.map((d, i) => {
          const done = d.tasks.length > 0 && d.tasks.every((t) => t.done);
          return (
            <button
              key={i}
              onClick={() => dayRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "start" })}
              className="shrink-0 px-2.5 py-1.5 rounded-lg border text-left btn-press"
              style={{
                borderColor: d.gate ? "var(--accent-strong)" : "var(--border-strong)",
                background: done ? "var(--accent-soft)" : "var(--surface)",
                minWidth: 78,
              }}
            >
              <div className="text-[10px] uppercase tracking-wider text-muted font-mono">{dayLabel(d, i)}</div>
              {d.date && <div className="text-[11px] font-medium tabular">{shortDate(d.date)}</div>}
              <div className="text-[10px] text-muted truncate max-w-[90px]">{d.channel || "prep"}</div>
            </button>
          );
        })}
      </div>

      {/* positioning + today's move */}
      <div className="grid md:grid-cols-2 gap-3 mb-5">
        {(plan.positioning?.tagline || plan.positioning?.one_liner) && (
          <div className="rounded-xl border bg-surface p-3.5" style={{ borderColor: "var(--border)" }}>
            <div className="text-[10.5px] uppercase tracking-[0.14em] text-muted font-medium mb-1.5">Positioning</div>
            {plan.positioning.tagline && <div className="text-[14px] font-semibold mb-1">{plan.positioning.tagline}</div>}
            {plan.positioning.one_liner && <div className="text-[12.5px] text-fg-dim leading-relaxed">{plan.positioning.one_liner}</div>}
            {plan.positioning.share_hook && <div className="text-[12px] text-muted mt-1.5">Hook: {plan.positioning.share_hook}</div>}
          </div>
        )}
        <div className="rounded-xl border p-3.5" style={{ borderColor: "var(--accent-strong)", background: "var(--accent-soft)" }}>
          <div className="flex items-center gap-1.5 mb-1.5">
            <Wand2 size={12} className="text-accent" />
            <span className="text-[10.5px] uppercase tracking-[0.14em] text-accent font-medium">Today&rsquo;s move</span>
            <button onClick={getMove} disabled={adviceBusy} className="ml-auto text-[11px] text-accent hover:opacity-80 flex items-center gap-1 btn-press">
              {adviceBusy ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
              {advice ? "refresh" : "get move"}
            </button>
          </div>
          {advice ? (
            <>
              <div className="text-[13px] font-medium leading-snug">{advice.move}</div>
              {advice.rationale && <div className="text-[11.5px] text-fg-dim mt-1">{advice.rationale}</div>}
            </>
          ) : (
            <div className="text-[12px] text-muted">Fill in tonight&rsquo;s numbers, then ask Pulse what to do next.</div>
          )}
        </div>
      </div>

      {/* day cards */}
      <div className="space-y-3">
        {plan.days.map((day, di) => (
          <div key={di} ref={(el) => { dayRefs.current[di] = el; }}>
            <DayCard
              day={day}
              dayIndex={di}
              metrics={m}
              onToggleTask={(ti) => mutateDay(di, (d) => ({ ...d, tasks: d.tasks.map((t, i) => (i === ti ? { ...t, done: !t.done } : t)) }))}
              onMetric={(key, val) => mutateDay(di, (d) => ({ ...d, metrics: { ...d.metrics, [key]: val } }))}
              onDraftPiece={(pi) => draftPiece(di, pi)}
              onPickVariant={(pi, vi) => setPieceVariant(di, pi, vi)}
            />
          </div>
        ))}
      </div>

      <details className="mt-5 rounded-xl border bg-surface" style={{ borderColor: "var(--border)" }}>
        <summary className="px-4 py-2.5 text-[12px] uppercase tracking-[0.12em] text-muted font-medium cursor-pointer select-none">
          Decision rules &amp; guardrails
        </summary>
        <div className="px-4 pb-4 space-y-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.12em] text-muted mb-1.5">Decision rules</div>
            <ul className="space-y-1 text-[12.5px] text-fg-dim">
              {plan.decision_rules.map((r, i) => <li key={i} className="flex gap-2"><ChevronRight size={13} className="text-accent mt-0.5 shrink-0" />{r}</li>)}
            </ul>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.12em] text-muted mb-1.5">Guardrails</div>
            <ul className="space-y-1 text-[12.5px] text-muted">
              {plan.guardrails.map((g, i) => <li key={i} className="flex gap-2"><AlertTriangle size={12} className="text-warn mt-0.5 shrink-0" />{g}</li>)}
            </ul>
          </div>
        </div>
      </details>
    </div>
  );
}

function DayCard({
  day,
  dayIndex,
  metrics,
  onToggleTask,
  onMetric,
  onDraftPiece,
  onPickVariant,
}: {
  day: LaunchDay;
  dayIndex: number;
  metrics: LaunchPlan["metrics"];
  onToggleTask: (ti: number) => void;
  onMetric: (key: "visits" | "north" | "loop" | "referrer", val: string) => void;
  onDraftPiece: (pi: number) => void;
  onPickVariant: (pi: number, vi: number) => void;
}) {
  const dayK = num(day.metrics.north) ? num(day.metrics.loop) / num(day.metrics.north) : 0;
  const dayF = num(day.metrics.visits) ? (num(day.metrics.north) / num(day.metrics.visits)) * 100 : 0;

  return (
    <div className="rounded-xl border bg-surface overflow-hidden scroll-mt-4" style={{ borderColor: day.gate ? "var(--accent-strong)" : "var(--border)" }}>
      <div className="px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="flex items-center gap-2.5">
          <div className="text-[13.5px] font-semibold flex-1">{day.title}</div>
          {day.date && <span className="text-[11px] text-muted font-mono tabular">{shortDate(day.date)}</span>}
          {day.channel && <span className="text-[10.5px] uppercase tracking-[0.14em] text-muted font-mono">{day.channel}</span>}
        </div>
        {day.goal && <div className="text-[12.5px] text-fg-dim mt-1.5"><span className="text-accent font-medium">Goal:</span> {day.goal}</div>}
        {day.rationale && <div className="text-[11.5px] text-muted mt-1 leading-relaxed">{day.rationale}</div>}
      </div>

      {day.tasks.length > 0 && (
        <ul className="px-4 py-2">
          {day.tasks.map((t, ti) => (
            <li key={ti} className="flex items-start gap-2.5 py-1.5">
              <button
                onClick={() => onToggleTask(ti)}
                className="w-[17px] h-[17px] rounded flex items-center justify-center shrink-0 mt-0.5 btn-press"
                style={{ border: "1px solid var(--border-strong)", background: t.done ? "var(--accent)" : "transparent", color: t.done ? "var(--accent-fg)" : "transparent" }}
                aria-pressed={t.done}
              >
                <Check size={11} />
              </button>
              <span className={`text-[13px] leading-snug ${t.done ? "line-through text-muted" : "text-fg-dim"}`}>{t.text}</span>
            </li>
          ))}
        </ul>
      )}

      {/* content pieces */}
      {day.content_pieces.length > 0 && (
        <div className="px-4 pb-3 space-y-2.5">
          <div className="text-[10.5px] uppercase tracking-[0.14em] text-muted font-medium">Content to ship</div>
          {day.content_pieces.map((piece, pi) => (
            <ContentPieceCard
              key={pi}
              piece={piece}
              onDraft={() => onDraftPiece(pi)}
              onPickVariant={(vi) => onPickVariant(pi, vi)}
            />
          ))}
        </div>
      )}

      {/* metrics */}
      <div className="grid grid-cols-4 gap-2 px-4 pb-3 pt-1" style={{ borderTop: "1px solid var(--border)" }}>
        <MetricInput label={metrics.visits} value={day.metrics.visits} onChange={(v) => onMetric("visits", v)} />
        <MetricInput label={metrics.north} value={day.metrics.north} onChange={(v) => onMetric("north", v)} />
        <MetricInput label={metrics.loop} value={day.metrics.loop} onChange={(v) => onMetric("loop", v)} />
        <div>
          <div className="text-[9.5px] uppercase tracking-[0.1em] text-muted mb-1">top referrer</div>
          <input className="li-input text-[12px] py-1" value={day.metrics.referrer} onChange={(e) => onMetric("referrer", e.target.value)} />
        </div>
      </div>
      {(num(day.metrics.north) > 0 || num(day.metrics.visits) > 0) && (
        <div className="flex gap-4 px-4 pb-3 text-[11px] font-mono text-muted">
          <span>K: <b className="text-fg">{dayK.toFixed(2)}</b></span>
          <span>funnel: <b className="text-fg">{dayF.toFixed(1)}%</b></span>
        </div>
      )}
      <span className="hidden">{dayIndex}</span>
    </div>
  );
}

function ContentPieceCard({
  piece,
  onDraft,
  onPickVariant,
}: {
  piece: LaunchContentPiece;
  onDraft: () => void;
  onPickVariant: (vi: number) => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const content = piece.variants[piece.chosen_variant] ?? piece.variants[0] ?? "";
  const openTo = CONTENT_OPEN[piece.kind];

  const draft = async () => {
    setBusy(true);
    try { await onDraft(); } finally { setBusy(false); }
  };

  const copyAndOpen = async () => {
    try { await navigator.clipboard.writeText(content); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {}
    if (openTo.url) window.open(openTo.url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="rounded-lg border" style={{ borderColor: "var(--border)", background: "var(--bg)" }}>
      <div className="flex items-center gap-2 px-3 py-2" style={{ borderBottom: piece.status === "drafted" ? "1px solid var(--border)" : "none" }}>
        <span
          className="text-[10px] uppercase tracking-[0.1em] font-mono font-medium px-1.5 py-0.5 rounded"
          style={{ background: "var(--elevated)", color: "var(--fg-dim)" }}
        >
          {CONTENT_LABEL[piece.kind]}
        </span>
        <span className="text-[12px] text-muted flex-1 truncate">{piece.brief}</span>
        {piece.status === "idea" ? (
          <button
            onClick={draft}
            disabled={busy}
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded btn-press disabled:opacity-50 shrink-0"
            style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent-strong)" }}
          >
            {busy ? <Loader2 size={10} className="animate-spin" /> : <Wand2 size={10} />}
            {busy ? "Writing…" : "Write it"}
          </button>
        ) : (
          <div className="flex items-center gap-1 shrink-0">
            <button onClick={draft} disabled={busy} className="p-1 rounded hover:bg-white/5 text-muted btn-press" title="regenerate">
              {busy ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
            </button>
            {openTo.url && (
              <button
                onClick={copyAndOpen}
                className="flex items-center gap-1 text-[11px] px-2 py-1 rounded btn-press"
                style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent-strong)" }}
                title={`copy and ${openTo.label.toLowerCase()}`}
              >
                {copied ? <Check size={10} /> : <ExternalLink size={10} />}
                {copied ? "Copied" : openTo.label}
              </button>
            )}
            {!openTo.url && (
              <button
                onClick={async () => { try { await navigator.clipboard.writeText(content); setCopied(true); setTimeout(() => setCopied(false), 1500); toast.push({ kind: "success", title: "Copied" }); } catch {} }}
                className="flex items-center gap-1 text-[11px] px-2 py-1 rounded btn-press"
                style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent-strong)" }}
              >
                {copied ? <Check size={10} /> : <Copy size={10} />} {copied ? "Copied" : "Copy"}
              </button>
            )}
          </div>
        )}
      </div>

      {piece.status === "drafted" && (
        <div className="px-3 py-2.5">
          {piece.variants.length > 1 && (
            <div className="inline-flex p-0.5 rounded-md border bg-surface mb-2" style={{ borderColor: "var(--border-strong)" }}>
              {piece.variants.map((_, vi) => (
                <button
                  key={vi}
                  onClick={() => onPickVariant(vi)}
                  className="px-2.5 py-0.5 rounded text-[11px] font-medium btn-press"
                  style={{
                    background: vi === piece.chosen_variant ? "var(--accent-soft)" : "transparent",
                    color: vi === piece.chosen_variant ? "var(--accent)" : "var(--muted-strong)",
                  }}
                >
                  {String.fromCharCode(65 + vi)}
                </button>
              ))}
            </div>
          )}
          <div className="text-[13px] whitespace-pre-wrap leading-relaxed text-fg-dim">{content}</div>
        </div>
      )}
    </div>
  );
}

/* ── small pieces ──────────────────────────────────────────────────── */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10.5px] uppercase tracking-[0.12em] text-muted font-medium mb-1">{label}</label>
      {children}
    </div>
  );
}

function ToggleField({ label, value, onChange }: { label: string; value: boolean | null | undefined; onChange: (v: boolean) => void }) {
  return (
    <Field label={label}>
      <div className="flex gap-1.5">
        {[{ v: true, t: "Yes" }, { v: false, t: "No" }].map((o) => (
          <button
            key={o.t}
            onClick={() => onChange(o.v)}
            className="flex-1 px-2 py-1.5 rounded text-[12px] font-medium btn-press"
            style={{
              background: value === o.v ? "var(--accent-soft)" : "var(--surface)",
              color: value === o.v ? "var(--accent)" : "var(--muted-strong)",
              border: `1px solid ${value === o.v ? "var(--accent-strong)" : "var(--border-strong)"}`,
            }}
          >
            {o.t}
          </button>
        ))}
      </div>
    </Field>
  );
}

function DerivedFact({ label, value, span }: { label: string; value: string; span?: boolean }) {
  return (
    <div className={span ? "col-span-2" : ""}>
      <div className="text-[10px] uppercase tracking-[0.12em] text-muted mb-0.5">{label}</div>
      <div className="text-[12px] text-fg-dim">{value}</div>
    </div>
  );
}

function Stat({ value, label, tone, big }: { value: string; label: string; tone?: "good" | "warn"; big?: boolean }) {
  const color = tone === "good" ? "var(--accent)" : tone === "warn" ? "var(--warn)" : "var(--fg)";
  return (
    <div>
      <div className={`font-semibold tabular ${big ? "text-[30px]" : "text-[18px]"} leading-none`} style={{ color }}>{value}</div>
      <div className="text-[10.5px] uppercase tracking-[0.1em] text-muted mt-1">{label}</div>
    </div>
  );
}

function MetricInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <div className="text-[9.5px] uppercase tracking-[0.1em] text-muted mb-1">{label}</div>
      <input type="number" min="0" className="li-input text-[14px] py-1 tabular" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

/* ── helpers ───────────────────────────────────────────────────────── */

function num(v: string): number {
  const n = parseFloat(v);
  return isNaN(n) ? 0 : n;
}

function dayLabel(d: LaunchDay, i: number): string {
  const m = d.title.match(/day\s*(\d+)/i);
  return m ? `Day ${m[1]}` : `Day ${i}`;
}

function shortDate(iso: string): string {
  try {
    return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function computeScore(plan: LaunchPlan) {
  let totN = 0, totL = 0, totV = 0, done = 0, total = 0;
  for (const d of plan.days) {
    totN += num(d.metrics.north);
    totL += num(d.metrics.loop);
    totV += num(d.metrics.visits);
    for (const t of d.tasks) {
      total++;
      if (t.done) done++;
    }
  }
  return {
    total_north: totN,
    total_loop: totL,
    total_visits: totV,
    k: totN ? totL / totN : 0,
    funnel_pct: totV ? (totN / totV) * 100 : 0,
    tasks_done: done,
    tasks_total: total,
    tasks_pct: total ? Math.round((done / total) * 100) : 0,
  };
}
