"use client";

import { useEffect, useRef, useState } from "react";
import {
  X,
  Copy,
  Check,
  Download,
  Edit3,
  Save,
  RefreshCw,
  FileText,
  Loader2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { DocumentKind, ProjectDocument } from "@/lib/api";
import { api } from "@/lib/api";
import { stripReasoning } from "@/lib/text";
import { Sheet } from "../ui/Sheet";
import { useToast } from "../ui/Toast";

export function DocumentSheet({
  projectId,
  kind,
  onClose,
  onLogConsole,
}: {
  projectId: number;
  kind: DocumentKind | null;
  onClose: () => void;
  onLogConsole?: (kind: "tool" | "result" | "meta" | "text", text: string) => void;
}) {
  const toast = useToast();
  const [doc, setDoc] = useState<ProjectDocument | null>(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [copied, setCopied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  // tracks which (project, kind) the current regen belongs to — late
  // responses for a different kind are ignored
  const regeneratingForRef = useRef<string | null>(null);
  const fetchedFor = useRef<string | null>(null);

  useEffect(() => {
    if (!kind) {
      setDoc(null);
      setEditing(false);
      setRegenerating(false);
      regeneratingForRef.current = null;
      fetchedFor.current = null;
      return;
    }
    const key = `${projectId}:${kind}`;
    // reset regen flag whenever we switch to a different kind
    setRegenerating(regeneratingForRef.current === key);
    if (fetchedFor.current === key) return;
    fetchedFor.current = key;

    let cancelled = false;
    setLoading(true);
    setDoc(null);
    onLogConsole?.("meta", `opening document: ${humanKind(kind)}…`);
    api
      .getDocumentByKind(projectId, kind)
      .then((d) => {
        if (cancelled) return;
        setDoc(d);
        setDraft(d.content_md);
      })
      .catch(() => {
        if (cancelled) return;
        setDoc(null);
        onLogConsole?.("meta", `${humanKind(kind)} not generated yet`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, kind, onLogConsole]);

  if (!kind) return null;

  const cleanContent = stripReasoning(doc?.content_md || "");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cleanContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
      onLogConsole?.("meta", `${humanKind(kind)} copied to clipboard`);
    } catch {
      toast.push({ kind: "error", title: "Copy failed" });
    }
  };

  const download = () => {
    if (!doc) return;
    const blob = new Blob([cleanContent], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${kind}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    onLogConsole?.("meta", `downloaded ${kind}.md`);
  };

  const save = async () => {
    if (!doc) return;
    onLogConsole?.("tool", `saving ${humanKind(kind)}…`);
    const updated = await api.updateDocument(doc.id, { content_md: draft });
    setDoc(updated);
    setEditing(false);
    toast.push({ kind: "success", title: "Document saved", detail: doc.title });
    onLogConsole?.("result", `✓ ${humanKind(kind)} saved`);
  };

  const regenerate = async () => {
    const ownKey = `${projectId}:${kind}`;
    regeneratingForRef.current = ownKey;
    setRegenerating(true);
    onLogConsole?.("tool", `Pulse is regenerating ${humanKind(kind)}…`);
    toast.push({
      kind: "info",
      title: "Regenerating",
      detail: humanKind(kind),
    });
    try {
      const fresh = await api.regenerateDocument(projectId, kind);
      // only apply result if we haven't switched to a different kind
      if (regeneratingForRef.current === ownKey) {
        setDoc(fresh);
        setDraft(fresh.content_md);
      }
      toast.push({
        kind: "success",
        title: "Regenerated",
        detail: humanKind(kind),
      });
      onLogConsole?.("result", `✓ ${humanKind(kind)} regenerated`);
    } catch (err) {
      toast.push({
        kind: "error",
        title: "Regeneration failed",
        detail: String((err as Error).message || err),
      });
      onLogConsole?.("meta", `regen failed: ${(err as Error).message}`);
    } finally {
      if (regeneratingForRef.current === ownKey) {
        regeneratingForRef.current = null;
        setRegenerating(false);
      }
    }
  };

  return (
    <Sheet open={!!kind} onClose={onClose} width="max-w-[720px]">
      <header
        className="flex items-center gap-3 px-5 py-3.5 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <FileText size={15} className="text-fg-dim" />
        <h2 className="text-[14px] font-semibold tracking-tight flex-1 truncate">
          {doc?.title || humanKind(kind)}
        </h2>

        <div className="flex items-center gap-0.5">
          <IconBtn icon={copied ? <Check size={13} className="text-accent" /> : <Copy size={13} />} label="copy" onClick={copy} />
          {!editing ? (
            <>
              <IconBtn icon={<Edit3 size={13} />} label="edit" onClick={() => setEditing(true)} />
              <IconBtn icon={<Download size={13} />} label="download" onClick={download} />
              <IconBtn
                icon={regenerating ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                label="regenerate"
                onClick={regenerate}
                disabled={regenerating}
              />
            </>
          ) : (
            <>
              <button
                onClick={() => {
                  setEditing(false);
                  setDraft(doc?.content_md || "");
                }}
                className="px-2 py-1 rounded text-[12px] text-muted hover:bg-white/5 btn-press"
              >
                Cancel
              </button>
              <button
                onClick={save}
                className="px-2 py-1 rounded text-[12px] flex items-center gap-1 btn-press"
                style={{
                  background: "var(--accent)",
                  color: "var(--accent-fg)",
                }}
              >
                <Save size={11} /> Save
              </button>
            </>
          )}
          <IconBtn icon={<X size={14} />} label="close" onClick={onClose} />
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-5">
        {loading ? (
          <DocumentSkeleton />
        ) : !doc ? (
          <EmptyDoc kind={kind} onRegenerate={regenerate} regenerating={regenerating} />
        ) : editing ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={28}
            className="w-full bg-surface border rounded-lg p-3.5 text-[13px] font-mono resize-y leading-relaxed"
            style={{ borderColor: "var(--border-strong)" }}
          />
        ) : (
          <div className="prose-pulse">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanContent}</ReactMarkdown>
          </div>
        )}
      </div>

      {doc && !editing && (
        <footer
          className="px-5 py-2.5 text-[10.5px] text-muted font-mono shrink-0"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          last updated {new Date(doc.updated_at).toLocaleString()}
        </footer>
      )}
    </Sheet>
  );
}

function IconBtn({
  icon,
  label,
  onClick,
  disabled,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className="p-1.5 rounded hover:bg-white/5 text-muted-strong btn-press disabled:opacity-40"
    >
      {icon}
    </button>
  );
}

function DocumentSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-6 shimmer w-1/3" />
      <div className="h-3 shimmer w-full" />
      <div className="h-3 shimmer w-11/12" />
      <div className="h-3 shimmer w-3/4" />
      <div className="h-5 shimmer w-1/4 mt-6" />
      <div className="h-3 shimmer w-full" />
      <div className="h-3 shimmer w-full" />
      <div className="h-3 shimmer w-2/3" />
    </div>
  );
}

function EmptyDoc({
  kind,
  onRegenerate,
  regenerating,
}: {
  kind: DocumentKind;
  onRegenerate: () => void;
  regenerating: boolean;
}) {
  return (
    <div className="py-12 text-center">
      <FileText size={22} className="mx-auto text-muted mb-2.5" />
      <div className="text-[13px] font-medium mb-1">
        {humanKind(kind)} hasn&apos;t been generated yet
      </div>
      <div className="text-[12px] text-muted max-w-sm mx-auto mb-4">
        Run a first dive on this project, or generate it now.
      </div>
      <button
        onClick={onRegenerate}
        disabled={regenerating}
        className="px-3 py-1.5 rounded border text-[12px] font-medium btn-press flex items-center gap-1.5 mx-auto"
        style={{
          borderColor: "var(--accent)",
          background: "var(--accent-soft)",
          color: "var(--accent)",
        }}
      >
        {regenerating ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
        Generate now
      </button>
    </div>
  );
}

function humanKind(kind: DocumentKind): string {
  return {
    product_information: "Product Information",
    competitor_analysis: "Competitor Analysis",
    brand_voice: "Brand Voice",
    marketing_strategy: "Marketing Strategy",
  }[kind];
}
