"use client";

import { useEffect, useState } from "react";
import { X, History, Loader2, TrendingUp, TrendingDown, Sparkles } from "lucide-react";
import { Sheet } from "../ui/Sheet";
import { api, type ProjectVersion } from "@/lib/api";

export function VersionsSheet({
  projectId,
  open,
  onClose,
}: {
  projectId: number;
  open: boolean;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [versions, setVersions] = useState<ProjectVersion[]>([]);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .listVersions(projectId)
      .then((r) => setVersions(r.versions))
      .catch(() => setVersions([]))
      .finally(() => setLoading(false));
  }, [open, projectId]);

  return (
    <Sheet open={open} onClose={onClose} width="max-w-[560px]">
      <header
        className="flex items-center gap-2.5 px-5 py-3.5 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <History size={15} className="text-fg-dim" />
        <h2 className="text-[14px] font-semibold tracking-tight flex-1">Version history</h2>
        <button onClick={onClose} className="p-1.5 rounded hover:bg-white/5 text-muted" aria-label="close">
          <X size={15} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-5">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={18} className="animate-spin text-accent" />
          </div>
        ) : versions.length === 0 ? (
          <div className="py-14 text-center">
            <History size={22} className="mx-auto text-muted mb-2.5" />
            <div className="text-[13px] font-medium mb-1">No versions yet</div>
            <div className="text-[12px] text-muted max-w-xs mx-auto">
              Each completed first dive or daily run snapshots a version here, with a day-over-day summary of what changed.
            </div>
          </div>
        ) : (
          <ol className="relative">
            {versions.map((v, i) => (
              <VersionRow key={v.id} version={v} latest={i === 0} />
            ))}
          </ol>
        )}
      </div>
    </Sheet>
  );
}

function VersionRow({ version, latest }: { version: ProjectVersion; latest: boolean }) {
  const s = version.snapshot || {};
  const d = s.deltas || {};
  return (
    <li className="relative pl-6 pb-5 last:pb-0">
      {/* timeline rail */}
      <span
        className="absolute left-[5px] top-5 bottom-0 w-px"
        style={{ background: "var(--border)" }}
        aria-hidden
      />
      <span
        className="absolute left-0 top-1.5 w-[11px] h-[11px] rounded-full"
        style={{
          background: latest ? "var(--accent)" : "var(--surface)",
          border: `2px solid ${latest ? "var(--accent)" : "var(--border-strong)"}`,
        }}
        aria-hidden
      />
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[13px] font-semibold">v{version.version_num}</span>
        <span
          className="text-[9.5px] uppercase tracking-[0.12em] font-mono px-1.5 py-0.5 rounded"
          style={{ background: "var(--elevated)", color: "var(--muted-strong)" }}
        >
          {version.kind === "first_dive" ? "first dive" : version.kind}
        </span>
        {latest && (
          <span
            className="text-[9.5px] uppercase tracking-[0.12em] font-mono px-1.5 py-0.5 rounded"
            style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
          >
            latest
          </span>
        )}
        <span className="text-[11px] text-muted font-mono ml-auto">{fmtDate(version.created_at)}</span>
      </div>

      <p className="text-[12.5px] text-fg-dim leading-relaxed mb-2">{version.summary_md}</p>

      {/* delta chips */}
      <div className="flex flex-wrap gap-1.5">
        {typeof s.actions_new === "number" && s.actions_new > 0 && (
          <Chip icon={<Sparkles size={10} />} text={`${s.actions_new} new action${s.actions_new === 1 ? "" : "s"}`} accent />
        )}
        {typeof d.seo_delta === "number" && d.seo_delta !== 0 && (
          <Chip
            icon={d.seo_delta > 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
            text={`SEO ${d.seo_delta > 0 ? "+" : ""}${d.seo_delta}`}
            tone={d.seo_delta > 0 ? "good" : "warn"}
          />
        )}
        {typeof d.traction_delta === "number" && d.traction_delta !== 0 && (
          <Chip
            icon={d.traction_delta > 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
            text={`${d.traction_delta > 0 ? "+" : ""}${d.traction_delta} mentions`}
            tone={d.traction_delta > 0 ? "good" : "warn"}
          />
        )}
        {typeof s.cost_usd === "number" && s.cost_usd > 0 && (
          <Chip text={fmtCost(s.cost_usd)} />
        )}
      </div>
    </li>
  );
}

function Chip({
  icon,
  text,
  accent,
  tone,
}: {
  icon?: React.ReactNode;
  text: string;
  accent?: boolean;
  tone?: "good" | "warn";
}) {
  const color =
    tone === "good" ? "var(--accent)" : tone === "warn" ? "var(--warn)" : accent ? "var(--accent)" : "var(--muted-strong)";
  const bg = accent || tone === "good" ? "var(--accent-soft)" : "var(--elevated)";
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10.5px] font-mono"
      style={{ background: bg, color }}
    >
      {icon}
      {text}
    </span>
  );
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtCost(usd: number): string {
  if (usd < 0.01) return `${(usd * 100).toFixed(2)}¢`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}
