"use client";

import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { Modal } from "./ui/Modal";
import { PulseLogo } from "./ui/PulseLogo";

export function AddProjectModal({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (url: string) => Promise<void>;
}) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await onCreate(url.trim());
      setUrl("");
    } catch (err) {
      setError(String((err as Error).message || err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add new project"
      maxWidth="max-w-md"
      footer={
        <>
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded text-[12px] text-muted hover:text-fg"
          >
            Cancel
          </button>
          <button
            onClick={() => submit()}
            disabled={busy || !url.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded font-medium text-[12px] disabled:opacity-50"
            style={{ background: "var(--accent)", color: "#0a0a0a" }}
          >
            {busy ? (
              <>
                <Loader2 size={12} className="animate-spin" /> Setting up…
              </>
            ) : (
              <>
                <Sparkles size={12} /> Start first dive
              </>
            )}
          </button>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-accent">
            <PulseLogo size={16} />
          </span>
          <span className="text-[11.5px] text-fg-dim">
            Drop a URL — Pulse will infer the rest.
          </span>
        </div>

        <label className="block">
          <span className="text-[10.5px] uppercase tracking-[0.14em] text-muted block mb-1.5 font-medium">
            Product URL
          </span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="acme.com"
            autoFocus
            disabled={busy}
            className="w-full bg-bg border rounded-lg px-3 py-2.5 outline-none focus:border-accent transition-colors font-mono text-[13.5px]"
            style={{ borderColor: "var(--border-strong)" }}
          />
        </label>

        <ul className="text-[11.5px] text-muted space-y-1 pt-1.5 list-none">
          <li>· crawl the site, infer name + description + competitors</li>
          <li>· audit on-page SEO and log fixes</li>
          <li>· extract brand voice from your existing copy</li>
          <li>· surface HN + Reddit threads worth replying to</li>
          <li>· draft a tweet, an article, and a 30-day strategy</li>
        </ul>

        {error && (
          <div className="text-danger text-[11.5px] font-mono">{error}</div>
        )}
      </form>
    </Modal>
  );
}
