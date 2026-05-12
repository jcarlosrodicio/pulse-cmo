"use client";

import type { CSSProperties, ReactNode } from "react";

export type Tone = "default" | "accent" | "warn" | "danger" | "info" | "muted";

// Map each tone to the theme-variable triple it should style with.
// All values reference tokens so themes (and palette tweaks) cascade.
const TONE_STYLES: Record<Tone, CSSProperties> = {
  default: {
    color: "var(--fg-dim)",
    background: "rgba(255, 255, 255, 0.05)",
    borderColor: "var(--border-strong)",
  },
  accent: {
    color: "var(--accent)",
    background: "var(--accent-soft)",
    borderColor: "var(--accent-strong)",
  },
  warn: {
    color: "var(--warn)",
    background: "var(--warn-soft)",
    borderColor: "var(--warn)",
  },
  danger: {
    color: "var(--danger)",
    background: "var(--danger-soft)",
    borderColor: "var(--danger)",
  },
  info: {
    color: "var(--info)",
    background: "var(--info-soft)",
    borderColor: "var(--info)",
  },
  muted: {
    color: "var(--muted)",
    background: "transparent",
    borderColor: "var(--border)",
  },
};

export function Badge({
  children,
  tone = "default",
  className = "",
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-[2px] rounded-[5px] border text-[10.5px] font-medium uppercase tracking-wider ${className}`}
      style={TONE_STYLES[tone]}
    >
      {children}
    </span>
  );
}
