"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Sparkles, Target } from "lucide-react";
import { api, type Brief } from "../lib/api";
import { Modal } from "./ui/Modal";

const METRICS = ["signups", "paying_customers", "revenue", "stars", "installs", "awareness"];
const PRODUCE = ["writing", "video", "design", "code"];

/**
 * The marketing-brief gate. Sits between "add project" and the first dive:
 * Pulse crawls the site, proposes what it can infer, and asks the founder for
 * the few things only they know (goal, baseline, what already flopped) BEFORE
 * the heavy run — so the dive optimizes for a real target instead of guessing.
 */
export function MarketingBriefModal({
  projectId,
  open,
  onClose,
  onStartDive,
}: {
  projectId: number | null;
  open: boolean;
  onClose: () => void;
  // Starts the first dive. Goes through the parent's run-stream hook so the
  // live console attaches — NOT a detached api.startRun (which left it idle).
  onStartDive: () => Promise<void> | void;
}) {
  const [loading, setLoading] = useState(true);
  const [suggesting, setSuggesting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [found, setFound] = useState<{ title: string; description: string } | null>(null);
  const [brief, setBrief] = useState<Brief>({});

  const set = <K extends keyof Brief>(k: K, v: Brief[K]) => setBrief((b) => ({ ...b, [k]: v }));

  useEffect(() => {
    if (!open || projectId === null) return;
    const ctrl = new AbortController();
    setLoading(true);
    setSuggesting(false);
    setError(null);
    setFound(null);
    setBrief({ horizon_days: 90, budget: "0", can_produce: ["writing"] });
    (async () => {
      try {
        // 1) fast crawl-only recon — shows the form near-instantly
        const r = await api.recon(projectId, ctrl.signal);
        if (ctrl.signal.aborted) return;
        setBrief((prev) => ({ ...prev, ...r.brief }));
        setFound({ title: r.crawl.title, description: r.crawl.description });
        setLoading(false);
      } catch (e) {
        if (ctrl.signal.aborted || (e as Error)?.name === "AbortError") return;
        setError(
          "Couldn't read the site (it may be unreachable). Fill the brief in yourself, or skip and dive.",
        );
        setLoading(false);
        return;
      }
      // 2) background LLM pre-fill — never blocks; fills empty fields when ready
      setSuggesting(true);
      try {
        const s = await api.suggestBrief(projectId, ctrl.signal);
        if (ctrl.signal.aborted) return;
        setBrief((prev) => {
          const next: Brief = { ...prev };
          for (const [k, v] of Object.entries(s.suggested || {})) {
            if (!v) continue;
            const cur = next[k as keyof Brief];
            if (cur === undefined || cur === "") {
              (next as Record<string, unknown>)[k] = v;
            }
          }
          return next;
        });
      } catch {
        /* best-effort pre-fill — the form is already usable */
      } finally {
        if (!ctrl.signal.aborted) setSuggesting(false);
      }
    })();
    return () => ctrl.abort();
  }, [open, projectId]);

  const startDive = useCallback(
    async (saveBrief: boolean) => {
      if (projectId === null) return;
      setBusy(true);
      setError(null);
      try {
        if (saveBrief) await api.updateProject(projectId, { brief });
        await onStartDive(); // parent's useRunStream.start("first_dive")
        onClose();
      } catch (e) {
        setError(String((e as Error).message || e));
        setBusy(false);
      }
    },
    [projectId, brief, onStartDive, onClose],
  );

  const toggleProduce = (p: string) => {
    const cur = brief.can_produce || [];
    set("can_produce", cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]);
  };

  return (
    <Modal
      open={open}
      onClose={busy ? () => {} : onClose}
      title="Before the dive — a 2-minute brief"
      maxWidth="max-w-2xl"
      footer={
        <>
          <button
            onClick={() => startDive(false)}
            disabled={busy || loading}
            className="px-3 py-1.5 rounded text-[12px] text-muted hover:text-fg disabled:opacity-50"
          >
            skip, just dive
          </button>
          <button
            onClick={() => startDive(true)}
            disabled={busy || loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded font-medium text-[12px] disabled:opacity-50"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            {busy ? (
              <>
                <Loader2 size={12} className="animate-spin" /> Starting dive…
              </>
            ) : (
              <>
                <Sparkles size={12} /> Save &amp; start the dive
              </>
            )}
          </button>
        </>
      }
    >
      {loading ? (
        <div className="flex items-center gap-2 text-muted text-[12.5px] py-8 justify-center">
          <Loader2 size={14} className="animate-spin text-accent" /> Reading your site…
        </div>
      ) : (
        <div className="space-y-4">
          {found && (found.title || found.description) && (
            <div className="rounded-lg border bg-surface p-3 text-[12px]" style={{ borderColor: "var(--border)" }}>
              <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-[0.14em] text-muted mb-1">
                <Target size={11} className="text-accent" /> Pulse read your site
              </div>
              {found.title && <div className="font-medium text-fg">{found.title}</div>}
              {found.description && <div className="text-fg-dim leading-relaxed mt-0.5">{found.description}</div>}
            </div>
          )}

          <p className="text-[11.5px] text-muted leading-relaxed">
            The dive runs on this. Pulse pre-filled what it could infer — fix anything wrong. The
            blanks are the things only you know; they make the difference between a real plan and
            generic advice.
          </p>

          {/* GOAL */}
          <Section title="The goal">
            <BField label="What does success look like in 90 days?" hint="Be concrete — a number if you can.">
              <textarea
                className="li-input min-h-[44px] resize-y"
                value={brief.goal || ""}
                onChange={(e) => set("goal", e.target.value)}
                placeholder="e.g. 500 developers making at least one real API call per week"
              />
            </BField>
            <div className="grid grid-cols-2 gap-3">
              <BField label="Success metric" loading={suggesting && !brief.goal_metric}>
                <select className="li-input" value={brief.goal_metric || ""} onChange={(e) => set("goal_metric", e.target.value)}>
                  <option value="">pick one</option>
                  {METRICS.map((m) => (
                    <option key={m} value={m}>
                      {m.replace("_", " ")}
                    </option>
                  ))}
                </select>
              </BField>
              <BField label="Horizon">
                <select
                  className="li-input"
                  value={brief.horizon_days || 90}
                  onChange={(e) => set("horizon_days", Number(e.target.value))}
                >
                  {[30, 60, 90].map((d) => (
                    <option key={d} value={d}>
                      {d} days
                    </option>
                  ))}
                </select>
              </BField>
            </div>
          </Section>

          {/* POSITIONING — prefilled guesses */}
          <Section title="Who it's for — Pulse's guess, edit if wrong">
            {suggesting && (
              <div className="flex items-center gap-1.5 text-[11px] text-muted -mt-1">
                <Loader2 size={11} className="animate-spin text-accent" /> Pulse is suggesting these
                in the background — type over anything it gets wrong.
              </div>
            )}
            <BField label="Ideal customer" loading={suggesting && !brief.icp}>
              <textarea
                className="li-input min-h-[40px] resize-y"
                value={brief.icp || ""}
                onChange={(e) => set("icp", e.target.value)}
                placeholder="a specific segment, not 'everyone'"
              />
            </BField>
            <div className="grid grid-cols-1 gap-3">
              <BField label="Explicitly NOT for" loading={suggesting && !brief.not_for}>
                <input className="li-input" value={brief.not_for || ""} onChange={(e) => set("not_for", e.target.value)} />
              </BField>
              <BField
                label="Your wedge"
                hint="the one thing to be remembered for vs the competition"
                loading={suggesting && !brief.wedge_hypothesis}
              >
                <textarea
                  className="li-input min-h-[40px] resize-y"
                  value={brief.wedge_hypothesis || ""}
                  onChange={(e) => set("wedge_hypothesis", e.target.value)}
                />
              </BField>
            </div>
          </Section>

          {/* REALITY */}
          <Section title="Where you actually are">
            <div className="grid grid-cols-2 gap-3">
              <BField label="Today's numbers" hint="traffic, signups, MRR — 'zero' is valid">
                <input className="li-input" value={brief.baseline || ""} onChange={(e) => set("baseline", e.target.value)} />
              </BField>
              <BField label="Hours/week you can spend">
                <input className="li-input" value={brief.hours_per_week || ""} onChange={(e) => set("hours_per_week", e.target.value)} placeholder="e.g. 10" />
              </BField>
            </div>
            <BField label="What you've already tried" hint="what worked, what flopped — so Pulse doesn't hand it back">
              <textarea
                className="li-input min-h-[40px] resize-y"
                value={brief.tried || ""}
                onChange={(e) => set("tried", e.target.value)}
              />
            </BField>
            <div className="grid grid-cols-2 gap-3">
              <BField label="Ad budget">
                <select className="li-input" value={brief.budget || "0"} onChange={(e) => set("budget", e.target.value)}>
                  {["0", "small", "funded"].map((b) => (
                    <option key={b} value={b}>
                      {b === "0" ? "none" : b}
                    </option>
                  ))}
                </select>
              </BField>
              <BField label="Off-limits" hint="channels you refuse">
                <input className="li-input" value={brief.off_limits || ""} onChange={(e) => set("off_limits", e.target.value)} placeholder="e.g. no TikTok" />
              </BField>
            </div>
            <BField label="You can make">
              <div className="flex flex-wrap gap-1.5">
                {PRODUCE.map((p) => {
                  const on = (brief.can_produce || []).includes(p);
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => toggleProduce(p)}
                      className="px-2.5 py-1 rounded text-[11.5px] font-medium btn-press"
                      style={{
                        background: on ? "var(--accent-soft)" : "var(--surface)",
                        color: on ? "var(--accent)" : "var(--muted-strong)",
                        border: `1px solid ${on ? "var(--accent-strong)" : "var(--border-strong)"}`,
                      }}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
            </BField>
            <BField label="Unfair advantages" hint="audience, community, design partners, a name people know">
              <input className="li-input" value={brief.assets || ""} onChange={(e) => set("assets", e.target.value)} />
            </BField>
          </Section>

          {error && <div className="text-danger text-[11.5px] font-mono">{error}</div>}
        </div>
      )}
    </Modal>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2.5">
      <div className="text-[10.5px] uppercase tracking-[0.14em] text-muted font-semibold">{title}</div>
      {children}
    </div>
  );
}

function BField({
  label,
  hint,
  loading,
  children,
}: {
  label: string;
  hint?: string;
  loading?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-[11px] text-fg-dim font-medium mb-1">
        {label}
        {hint && <span className="text-muted font-normal"> — {hint}</span>}
      </label>
      <div className="relative">
        {children}
        {loading && (
          <>
            <span
              className="shimmer absolute inset-0 rounded-lg pointer-events-none"
              aria-hidden="true"
            />
            <Loader2
              size={12}
              className="animate-spin text-accent absolute right-2 top-2 pointer-events-none"
              aria-hidden="true"
            />
          </>
        )}
      </div>
    </div>
  );
}
