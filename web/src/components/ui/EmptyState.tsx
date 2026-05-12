"use client";

import type { ReactNode } from "react";

export function EmptyState({
  icon,
  title,
  subtitle,
  hint,
  cta,
  variant = "dashed",
}: {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  hint?: string;
  cta?: { label: string; onClick: () => void };
  variant?: "dashed" | "ghost";
}) {
  return (
    <div
      className={`relative py-12 px-6 text-center rounded-xl ${
        variant === "dashed" ? "border border-dashed bg-grid" : ""
      }`}
      style={
        variant === "dashed"
          ? { borderColor: "var(--border-strong)" }
          : undefined
      }
    >
      {icon && (
        <div className="flex justify-center mb-2.5 text-muted-strong">{icon}</div>
      )}
      <div className="text-[13px] font-medium text-fg mb-1 tracking-tight">{title}</div>
      {subtitle && (
        <div className="text-[12px] text-muted max-w-sm mx-auto leading-relaxed">
          {subtitle}
        </div>
      )}
      {hint && (
        <div className="text-[10.5px] uppercase tracking-[0.16em] text-muted mt-3 font-mono">
          {hint}
        </div>
      )}
      {cta && (
        <button
          onClick={cta.onClick}
          className="mt-4 px-3 py-1.5 rounded text-[12px] font-medium border btn-press"
          style={{
            borderColor: "var(--accent)",
            background: "var(--accent-soft)",
            color: "var(--accent)",
          }}
        >
          {cta.label}
        </button>
      )}
    </div>
  );
}
