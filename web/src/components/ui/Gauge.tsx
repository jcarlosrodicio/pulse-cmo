"use client";

export function Gauge({
  value,
  label,
  size = 56,
  strokeWidth = 4,
}: {
  value: number | null | undefined;
  label?: string;
  size?: number;
  strokeWidth?: number;
}) {
  const v = typeof value === "number" ? Math.max(0, Math.min(100, value)) : null;
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const dash = v === null ? 0 : (v / 100) * circ;

  const tier =
    v === null ? "muted" : v >= 90 ? "good" : v >= 50 ? "mid" : "bad";

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="gauge" style={{ width: size, height: size }}>
        <svg viewBox={`0 0 ${size} ${size}`}>
          <circle
            className="gauge-track"
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            strokeWidth={strokeWidth}
            stroke="currentColor"
            opacity={0.08}
          />
          <circle
            className={`gauge-arc gauge-${tier}`}
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            stroke="currentColor"
            strokeDasharray={`${dash} ${circ - dash}`}
          />
        </svg>
        <div
          className="absolute inset-0 flex items-center justify-center text-[14px] font-medium tabular"
          style={{ color: v === null ? "var(--muted)" : "var(--fg)" }}
        >
          {v === null ? "—" : v}
        </div>
      </div>
      {label && (
        <span className="text-[10.5px] uppercase tracking-wider text-muted">
          {label}
        </span>
      )}
    </div>
  );
}
