"use client";

import { useEffect, useState } from "react";
import { RotateCcw, Trash2, AlertTriangle, Loader2 } from "lucide-react";
import { api, type Project } from "../lib/api";
import { Modal } from "./ui/Modal";

/** A short confirm token: the first word of the name (e.g. "openadapter"),
 * else the domain slug, else "delete". Beats typing a long generated title. */
function confirmToken(project: Project): string {
  const firstWord = (project.name || "").trim().split(/[\s—–-]+/)[0];
  if (firstWord && firstWord.length >= 2) return firstWord.toLowerCase();
  try {
    const slug = new URL(project.url).hostname.replace(/^www\./, "").split(".")[0];
    if (slug) return slug.toLowerCase();
  } catch {
    /* ignore bad url */
  }
  return "delete";
}

/**
 * Manage-project popup: redo the first dive (safe) or permanently delete the
 * project (destructive — gated behind typing the exact project name, GitHub
 * style). One place for "start over" vs "wipe it".
 */
export function ProjectDangerModal({
  project,
  open,
  onClose,
  onRedo,
  onDeleted,
}: {
  project: Project;
  open: boolean;
  onClose: () => void;
  onRedo: () => void;
  onDeleted: () => Promise<void> | void;
}) {
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setConfirm("");
      setError(null);
      setBusy(false);
    }
  }, [open]);

  // A short, recognizable token instead of the long generated name: the first
  // word of the name (e.g. "openadapter"), falling back to the domain slug.
  const token = confirmToken(project);
  const match = confirm.trim().toLowerCase() === token.toLowerCase();

  async function doDelete() {
    if (!match || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteProject(project.id);
      await onDeleted();
      onClose();
    } catch (e) {
      setError(String((e as Error).message || e));
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={busy ? () => {} : onClose}
      title="Manage project"
      maxWidth="max-w-md"
      footer={
        <button
          onClick={onClose}
          disabled={busy}
          className="px-3 py-1.5 rounded text-[12px] text-muted hover:text-fg disabled:opacity-50"
        >
          Close
        </button>
      }
    >
      <div className="space-y-5">
        {/* Redo — the safe option */}
        <div className="rounded-lg border bg-surface p-3.5" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center gap-2 mb-1">
            <RotateCcw size={14} className="text-accent" />
            <span className="text-[13px] font-semibold">Redo first dive</span>
          </div>
          <p className="text-[11.5px] text-muted leading-relaxed mb-2.5">
            Keep the project but re-run the full scan from scratch — crawl, brand voice, audits,
            positioning, and a fresh plan. Regenerates the documents; the project and its history
            stay.
          </p>
          <button
            onClick={() => {
              onRedo();
              onClose();
            }}
            disabled={busy}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded font-medium text-[12px] btn-press disabled:opacity-50"
            style={{
              background: "var(--accent-soft)",
              color: "var(--accent)",
              border: "1px solid var(--accent-strong)",
            }}
          >
            <RotateCcw size={12} /> Redo first dive
          </button>
        </div>

        {/* Danger zone */}
        <div
          className="rounded-lg border p-3.5"
          style={{ borderColor: "var(--danger)", background: "var(--danger-soft)" }}
        >
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle size={14} style={{ color: "var(--danger)" }} />
            <span className="text-[13px] font-semibold" style={{ color: "var(--danger)" }}>
              Delete this project
            </span>
          </div>
          <p className="text-[11.5px] text-muted leading-relaxed mb-3">
            Permanently wipes <span className="text-fg font-medium">{project.name}</span> and
            everything in it: actions, documents, runs, versions, the launch campaign, chat, and
            usage history. This cannot be undone.
          </p>
          <label className="block text-[11px] text-fg-dim mb-1.5">
            Type <span className="font-mono text-fg">{token}</span> to confirm
          </label>
          <input
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder={token}
            disabled={busy}
            autoComplete="off"
            spellCheck={false}
            className="w-full bg-bg border rounded-lg px-3 py-2 outline-none font-mono text-[12.5px] mb-3 transition-colors"
            style={{ borderColor: match ? "var(--danger)" : "var(--border-strong)" }}
          />
          <button
            onClick={doDelete}
            disabled={!match || busy}
            className="flex items-center gap-1.5 px-3 py-2 rounded font-semibold text-[12px] btn-press w-full justify-center disabled:cursor-not-allowed"
            style={{
              background: match ? "var(--danger)" : "var(--surface)",
              color: match ? "var(--danger-fg)" : "var(--muted-strong)",
              border: "1px solid var(--danger)",
              opacity: match || busy ? 1 : 0.5,
            }}
          >
            {busy ? (
              <>
                <Loader2 size={12} className="animate-spin" /> Deleting…
              </>
            ) : (
              <>
                <Trash2 size={12} /> Delete project permanently
              </>
            )}
          </button>
          {error && <div className="text-danger text-[11px] font-mono mt-2">{error}</div>}
        </div>
      </div>
    </Modal>
  );
}
