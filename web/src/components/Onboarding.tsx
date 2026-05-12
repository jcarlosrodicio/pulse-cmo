"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { PulseLogo } from "./ui/PulseLogo";

export function Onboarding({
  onCreate,
}: {
  onCreate: (url: string) => Promise<void>;
}) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) {
      setError("URL is required");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onCreate(url.trim());
    } catch (err) {
      setError(String((err as Error).message || err));
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-5 relative overflow-hidden">
      {/* subtle grid backdrop */}
      <div className="absolute inset-0 bg-grid opacity-50" />
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 0%, var(--bg) 70%)",
        }}
      />

      <form
        onSubmit={submit}
        className="relative w-full max-w-md bg-surface border rounded-2xl p-7 modal-card"
        style={{ borderColor: "var(--border-strong)" }}
      >
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-accent">
            <PulseLogo size={18} />
          </span>
          <span className="font-mono text-[11px] tracking-[0.16em] uppercase text-muted">
            pulse
          </span>
        </div>
        <h1 className="text-[24px] font-semibold tracking-tight mb-1.5 leading-tight">
          Your daily heartbeat
        </h1>
        <p className="text-[13px] text-fg-dim mb-6 leading-relaxed">
          Give me your site. I&apos;ll audit it, find HN threads worth replying to,
          draft content in your voice, and hand you 3-5 actions every morning.
        </p>

        <label className="block mb-5">
          <span className="text-[10.5px] uppercase tracking-[0.14em] text-muted block mb-1.5 font-medium">
            Product URL
          </span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="openadapter.dev"
            className="w-full bg-bg border rounded-lg px-3 py-2.5 outline-none focus:border-accent transition-colors font-mono text-[13px]"
            style={{ borderColor: "var(--border-strong)" }}
            autoFocus
            required
          />
          <p className="text-[11px] text-muted mt-1.5">
            We&apos;ll infer the rest — name, description, competitors, voice — from your site.
          </p>
        </label>

        {error && (
          <div className="text-danger text-[11.5px] mb-3 font-mono">{error}</div>
        )}

        <button
          type="submit"
          disabled={busy || !url.trim()}
          className="w-full py-2.5 rounded-lg font-medium text-[13.5px] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors border"
          style={{
            background: "var(--accent)",
            color: "#0a0a0a",
            borderColor: "var(--accent)",
          }}
        >
          {busy ? (
            <>
              <Loader2 size={14} className="animate-spin" /> setting up…
            </>
          ) : (
            "Start first dive"
          )}
        </button>

        <p className="text-[10.5px] text-muted mt-4 text-center font-mono">
          a 1-2 minute scan of your site
        </p>
      </form>
    </div>
  );
}
