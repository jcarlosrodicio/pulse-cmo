"use client";

import { Modal } from "./Modal";

type Group = {
  title: string;
  rows: { keys: string[]; label: string }[];
};

const isMac = typeof navigator !== "undefined" && /mac/i.test(navigator.platform);
const MOD = isMac ? "⌘" : "Ctrl";

function groups(): Group[] {
  return [
    {
      title: "Navigation",
      rows: [
        { keys: [MOD, "K"], label: "Open chat (CMO)" },
        { keys: [MOD, "N"], label: "Add new project" },
        { keys: ["Esc"], label: "Close sheet or modal" },
      ],
    },
    {
      title: "Run",
      rows: [
        { keys: ["G"], label: "Run now (daily pass)" },
        { keys: ["R"], label: "Refresh actions feed" },
      ],
    },
    {
      title: "Actions",
      rows: [
        { keys: [MOD, "/"], label: "Search actions" },
        { keys: ["?"], label: "Toggle this overlay" },
      ],
    },
    {
      title: "Chat composer",
      rows: [
        { keys: ["↵"], label: "Send message" },
        { keys: ["⇧", "↵"], label: "Newline" },
      ],
    },
  ];
}

export function KeyboardShortcuts({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title="Keyboard shortcuts" maxWidth="max-w-lg">
      <div className="space-y-5">
        {groups().map((g) => (
          <div key={g.title}>
            <h3 className="text-[10.5px] uppercase tracking-[0.16em] text-muted font-medium mb-2">
              {g.title}
            </h3>
            <ul className="space-y-1.5">
              {g.rows.map((row) => (
                <li
                  key={row.label}
                  className="flex items-center justify-between text-[12.5px] py-1.5 border-b last:border-b-0"
                  style={{ borderColor: "var(--border)" }}
                >
                  <span className="text-fg-dim">{row.label}</span>
                  <div className="flex gap-1">
                    {row.keys.map((k, i) => (
                      <kbd
                        key={i}
                        className="px-1.5 py-0.5 rounded font-mono text-[11px] bg-white/5 border"
                        style={{ borderColor: "var(--border-strong)", color: "var(--fg)" }}
                      >
                        {k}
                      </kbd>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Modal>
  );
}
