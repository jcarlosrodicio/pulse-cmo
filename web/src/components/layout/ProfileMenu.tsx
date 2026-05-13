"use client";

import { useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  Settings2,
  Sun,
  Moon,
  Plug,
  Sparkles,
  Activity,
} from "lucide-react";
import { useTheme } from "../ui/Theme";

export function ProfileMenu({
  costUsd,
  tokens,
  llmCalls,
  onOpenSettings,
}: {
  costUsd: number | null;
  tokens: number | null;
  llmCalls?: number | null;
  onOpenSettings: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { theme, toggle } = useTheme();

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const costText = formatCostShort(costUsd);
  const tokenText = tokens && tokens > 0 ? formatTokens(tokens) : null;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-white/5 btn-press"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-[10.5px] font-semibold font-mono"
          style={{
            background: "var(--accent-soft)",
            color: "var(--accent)",
            border: "1px solid var(--accent-strong)",
          }}
          title="You"
        >
          P
        </div>
        <div className="hidden sm:flex flex-col items-start leading-tight">
          <span className="text-[11px] text-muted-strong font-mono tabular">
            {costText || "—"}
          </span>
          {tokenText && (
            <span className="text-[9.5px] text-muted font-mono tabular">
              {tokenText} tok
            </span>
          )}
        </div>
        <ChevronDown size={11} className="text-muted-strong" />
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-1.5 w-[260px] rounded-xl border shadow-lg z-50"
          style={{
            background: "var(--surface)",
            borderColor: "var(--border-strong)",
            boxShadow: "0 8px 24px rgba(0,0,0,0.25)",
          }}
          role="menu"
        >
          {/* usage strip */}
          <div
            className="px-3.5 py-3"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <div className="flex items-center gap-1.5 text-[10.5px] uppercase tracking-[0.14em] text-muted font-medium mb-2">
              <Activity size={11} /> Last run
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
              <Stat label="cost" value={costText || "—"} accent />
              <Stat label="tokens" value={tokenText || "—"} />
              <Stat label="calls" value={llmCalls != null ? String(llmCalls) : "—"} />
            </div>
          </div>

          {/* theme */}
          <button
            onClick={() => {
              toggle();
            }}
            className="w-full flex items-center gap-2.5 px-3.5 py-2.5 hover:bg-white/4 text-left btn-press"
            role="menuitem"
          >
            {theme === "dark" ? <Moon size={13} /> : <Sun size={13} />}
            <span className="flex-1 text-[12.5px]">Theme</span>
            <span className="text-[11.5px] text-muted capitalize">{theme}</span>
          </button>

          {/* providers / settings */}
          <button
            onClick={() => {
              setOpen(false);
              onOpenSettings();
            }}
            className="w-full flex items-center gap-2.5 px-3.5 py-2.5 hover:bg-white/4 text-left btn-press"
            role="menuitem"
          >
            <Plug size={13} />
            <span className="flex-1 text-[12.5px]">Providers</span>
            <span className="text-[10.5px] text-muted">Configure</span>
          </button>

          {/* footer */}
          <div
            className="px-3.5 py-2 flex items-center gap-1.5 text-[10.5px] text-muted"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            <Sparkles size={10} className="text-accent" />
            Pulse · indie growth ops
            <div className="flex-1" />
            <Settings2 size={10} />
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div
        className="text-[13px] font-medium font-mono tabular leading-tight"
        style={{ color: accent ? "var(--accent)" : "var(--fg)" }}
      >
        {value}
      </div>
      <div className="text-[9.5px] text-muted uppercase tracking-[0.12em] mt-0.5">{label}</div>
    </div>
  );
}

function formatCostShort(usd: number | null | undefined): string | null {
  if (usd == null || usd === 0) return null;
  if (usd < 0.01) return `${(usd * 100).toFixed(2)}¢`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return (n / 1_000_000).toFixed(2).replace(/\.00$/, "") + "M";
}
