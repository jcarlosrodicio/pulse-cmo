"use client";

import { useState } from "react";
import { Loader2, LineChart } from "lucide-react";
import { type WeeklySnapshot } from "@/lib/api";
import { Modal } from "../ui/Modal";

/**
 * The reality loop's input. The founder logs the week's real numbers; Pulse
 * reads them against this week's moves, makes the call (continue / adjust /
 * kill), and writes next week's plan. This is what turns Pulse from a content
 * bot into an operator — the open loop is closed here.
 */
export function WeeklyReviewModal({
  open,
  onClose,
  weekNum,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  weekNum: number | null;
  // Wired to useRunStream.start("weekly_review", {instruction}) so the call
  // streams live in the console, exactly like a dive.
  onSubmit: (snapshot: WeeklySnapshot) => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);
  const [snap, setSnap] = useState<WeeklySnapshot>({});
  const set = <K extends keyof WeeklySnapshot>(k: K, v: WeeklySnapshot[K]) =>
    setSnap((s) => ({ ...s, [k]: v }));

  const submit = async () => {
    setBusy(true);
    try {
      await onSubmit(snap);
      setSnap({});
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={busy ? () => {} : onClose}
      title={weekNum ? `Log week ${weekNum} — the real numbers` : "Log this week"}
      maxWidth="max-w-lg"
      footer={
        <>
          <button
            onClick={onClose}
            disabled={busy}
            className="px-3 py-1.5 rounded text-[12px] text-muted hover:text-fg disabled:opacity-50"
          >
            cancel
          </button>
          <button
            onClick={submit}
            disabled={busy}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded font-medium text-[12px] disabled:opacity-50"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            {busy ? (
              <>
                <Loader2 size={12} className="animate-spin" /> Reading your week…
              </>
            ) : (
              <>
                <LineChart size={12} /> Make the call
              </>
            )}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-[11.5px] text-muted leading-relaxed">
          Pulse reads these against this week&apos;s moves, makes the call — continue, adjust, or
          kill the bet — and writes next week&apos;s plan. Rough numbers are fine; even
          &ldquo;zero&rdquo; is a real signal.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <RField label="New signups / users" hint="vs last week">
            <input
              className="li-input"
              value={snap.signups || ""}
              onChange={(e) => set("signups", e.target.value)}
              placeholder="e.g. 6 (up from 2)"
            />
          </RField>
          <RField label="Visitors / traffic">
            <input
              className="li-input"
              value={snap.visitors || ""}
              onChange={(e) => set("visitors", e.target.value)}
              placeholder="e.g. ~210"
            />
          </RField>
        </div>
        <RField label="Where did they come from?" hint="the channels that actually drove it">
          <input
            className="li-input"
            value={snap.top_sources || ""}
            onChange={(e) => set("top_sources", e.target.value)}
            placeholder="e.g. Hacker News, r/LocalLLaMA, direct"
          />
        </RField>
        <RField label="What did you ship / do this week?" hint="so Pulse can attribute results to moves">
          <textarea
            className="li-input min-h-[60px] resize-y"
            value={snap.shipped || ""}
            onChange={(e) => set("shipped", e.target.value)}
            placeholder="e.g. posted the Show HN, replied in comments, shipped the share card"
          />
        </RField>
        <RField label="Anything else?" hint="optional">
          <input
            className="li-input"
            value={snap.notes || ""}
            onChange={(e) => set("notes", e.target.value)}
          />
        </RField>
      </div>
    </Modal>
  );
}

function RField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-[11px] text-fg-dim font-medium mb-1">
        {label}
        {hint && <span className="text-muted font-normal"> — {hint}</span>}
      </label>
      {children}
    </div>
  );
}
