"use client";

import type { ActionType } from "@/lib/api";
import { metaFor } from "@/lib/actionTypes";

export function ChannelIcon({
  kind,
  size = 22,
}: {
  kind: ActionType;
  size?: number;
}) {
  const m = metaFor(kind);
  return (
    <div
      className="inline-flex items-center justify-center rounded-md font-medium shrink-0"
      style={{
        width: size,
        height: size,
        background: m.tintBg,
        color: m.tint,
        fontSize: size * 0.5,
        fontFamily: "var(--font-mono)",
        letterSpacing: 0,
      }}
    >
      {m.shortLabel}
    </div>
  );
}
