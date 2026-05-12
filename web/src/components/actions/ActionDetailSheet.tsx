"use client";

import { useEffect, useRef, useState } from "react";
import {
  X,
  Copy,
  Check,
  ExternalLink,
  Loader2,
  Sparkles,
  Edit3,
  Save,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Action } from "@/lib/api";
import { api } from "@/lib/api";
import { stripReasoning } from "@/lib/text";
import { Sheet } from "../ui/Sheet";
import { ChannelIcon } from "../ui/ChannelIcon";
import { Badge } from "../ui/Badge";

const ACTION_LABEL: Record<Action["action_type"], string> = {
  seo_fix: "SEO & GEO Recommendations",
  tweet: "X Writer",
  hn_post: "Hacker News",
  hn_opportunity: "Hacker News",
  reddit_opportunity: "Reddit Opportunity",
  reddit_reply: "Reddit Reply Draft",
  linkedin: "LinkedIn Writer",
  article: "Articles",
  market_gap: "Positioning Gap",
  strategy: "Strategy",
};

export function ActionDetailSheet({
  action,
  onClose,
  onStatusChange,
  onContentChange,
}: {
  action: Action | null;
  onClose: () => void;
  onStatusChange: (a: Action, status: Action["status"]) => void;
  onContentChange: (a: Action, content: string, title?: string) => void;
}) {
  const [detail, setDetail] = useState<string | null>(null);
  const [expanding, setExpanding] = useState(false);
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const fetchedFor = useRef<number | null>(null);

  useEffect(() => {
    if (!action) {
      setDetail(null);
      setEditing(false);
      return;
    }
    setDetail(action.detail_md ?? null);
    setEditTitle(action.title);
    setEditContent(action.content);

    const needsExpand =
      (action.action_type === "seo_fix" ||
        action.action_type === "hn_opportunity" ||
        action.action_type === "reddit_opportunity" ||
        action.action_type === "market_gap") &&
      !action.detail_md &&
      fetchedFor.current !== action.id;

    if (needsExpand) {
      fetchedFor.current = action.id;
      setExpanding(true);
      api
        .expandAction(action.id)
        .then((res) => setDetail(res.detail_md))
        .catch(() => setDetail(null))
        .finally(() => setExpanding(false));
    }
  }, [action]);

  if (!action) return null;

  const sourceUrl = (action.context as { hn_url?: string })?.hn_url;
  const severity = (action.context as { severity?: string })?.severity;
  const variants =
    (action.context as { variants?: string[] })?.variants || [];
  const chosenVariant =
    (action.context as { chosen_variant?: number })?.chosen_variant ?? 0;
  const hasVariants = variants.length > 1;
  const cleanContent = stripReasoning(action.content);
  const cleanDetail = stripReasoning(detail);
  const isMarkdownBody =
    action.action_type === "article" ||
    action.action_type === "strategy" ||
    action.action_type === "market_gap" ||
    action.action_type === "reddit_opportunity" ||
    action.action_type === "hn_opportunity";
  const showDetailBlock =
    (action.action_type === "seo_fix" ||
      action.action_type === "hn_opportunity" ||
      action.action_type === "reddit_opportunity" ||
      action.action_type === "market_gap") &&
    (detail || expanding);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cleanContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // noop
    }
  };

  const saveEdit = () => {
    onContentChange(action, editContent, editTitle);
    setEditing(false);
  };

  return (
    <Sheet open={!!action} onClose={onClose} width="max-w-[680px]">
      <header
        className="flex items-center gap-3 px-5 py-3.5 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <ChannelIcon kind={action.action_type} size={24} />
        <h2 className="text-[14px] font-semibold tracking-tight flex-1">
          {ACTION_LABEL[action.action_type]}
        </h2>

        <div className="flex items-center gap-1">
          {action.status !== "shipped" ? (
            <button
              onClick={() => onStatusChange(action, "shipped")}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded border bg-surface card-hover text-[12px] font-medium"
              style={{ borderColor: "var(--border-strong)" }}
            >
              <Check size={12} className="text-accent" /> Mark Complete
            </button>
          ) : (
            <Badge tone="accent">Shipped</Badge>
          )}
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-white/5 text-muted"
            aria-label="close"
          >
            <X size={15} />
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        {/* meta */}
        <div className="flex items-center gap-2 text-[11px] text-muted mb-3">
          {severity && (
            <Badge
              tone={severity === "high" ? "danger" : severity === "medium" ? "warn" : "muted"}
            >
              {severity}
            </Badge>
          )}
          <span className="font-mono">
            #{action.id} ·{" "}
            {new Date(action.created_at).toLocaleString(undefined, {
              month: "short",
              day: "numeric",
              hour: "numeric",
              minute: "2-digit",
            })}
          </span>
          {sourceUrl && (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-fg-dim hover:text-fg"
            >
              <ExternalLink size={11} /> source
            </a>
          )}
        </div>

        {/* title */}
        {!editing ? (
          <h1 className="text-[20px] font-semibold tracking-tight leading-tight mb-4">
            {action.title}
          </h1>
        ) : (
          <input
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            className="w-full bg-surface border rounded p-2 mb-3 text-[18px] font-medium"
            style={{ borderColor: "var(--border-strong)" }}
          />
        )}

        {/* A/B variant tabs */}
        {!editing && hasVariants && (
          <VariantTabs
            count={variants.length}
            chosen={chosenVariant}
            onPick={async (i) => {
              if (i === chosenVariant) return;
              const updated = await import("@/lib/api").then(({ api }) =>
                api.updateAction(action.id, { chosen_variant: i }),
              );
              // Surface optimistically to the parent via onContentChange
              // (also persists title unchanged).
              onContentChange(updated, updated.content, updated.title);
            }}
          />
        )}

        {/* content card with copy/edit */}
        <div
          className="rounded-xl border bg-surface mb-4 overflow-hidden"
          style={{ borderColor: "var(--border)" }}
        >
          <div
            className="flex items-center gap-1 px-3 py-2"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <span className="text-[10.5px] uppercase tracking-[0.14em] text-muted font-medium">
              {editing ? "Editing" : "Draft"}
            </span>
            <div className="flex-1" />
            {!editing ? (
              <>
                <button
                  onClick={copy}
                  className="flex items-center gap-1 px-2 py-0.5 rounded text-[11.5px] text-fg-dim hover:bg-white/5"
                >
                  {copied ? <Check size={11} className="text-accent" /> : <Copy size={11} />}
                  {copied ? "Copied" : "Copy"}
                </button>
                <button
                  onClick={() => setEditing(true)}
                  className="flex items-center gap-1 px-2 py-0.5 rounded text-[11.5px] text-fg-dim hover:bg-white/5"
                >
                  <Edit3 size={11} /> Edit
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => {
                    setEditing(false);
                    setEditTitle(action.title);
                    setEditContent(action.content);
                  }}
                  className="px-2 py-0.5 rounded text-[11.5px] text-muted hover:bg-white/5"
                >
                  Cancel
                </button>
                <button
                  onClick={saveEdit}
                  className="flex items-center gap-1 px-2 py-0.5 rounded text-[11.5px] text-accent hover:bg-white/5"
                >
                  <Save size={11} /> Save
                </button>
              </>
            )}
          </div>

          <div className="p-4">
            {editing ? (
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                rows={12}
                className="w-full bg-bg border-0 outline-none text-[13.5px] font-mono resize-y leading-relaxed"
                style={{ minHeight: 200 }}
              />
            ) : isMarkdownBody ? (
              <div className="prose-pulse">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanContent}</ReactMarkdown>
              </div>
            ) : (
              <div className="text-[13.5px] whitespace-pre-wrap leading-relaxed">
                {cleanContent}
              </div>
            )}
          </div>
        </div>

        {/* expanded detail (SEO / HN) */}
        {showDetailBlock && (
          <div className="mb-4">
            <div className="flex items-center gap-1.5 mb-2">
              <Sparkles size={12} className="text-accent" />
              <span className="text-[10.5px] uppercase tracking-[0.14em] text-muted font-medium">
                Step-by-step guide
              </span>
            </div>
            {expanding ? (
              <div className="space-y-2">
                <div className="h-3 shimmer w-3/4" />
                <div className="h-3 shimmer w-full" />
                <div className="h-3 shimmer w-1/2" />
              </div>
            ) : cleanDetail ? (
              <div className="prose-pulse">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanDetail}</ReactMarkdown>
              </div>
            ) : null}
          </div>
        )}

        {/* dismiss footer */}
        {action.status === "pending" && (
          <div className="pt-3" style={{ borderTop: "1px solid var(--border)" }}>
            <button
              onClick={() => onStatusChange(action, "dismissed")}
              className="text-[11.5px] text-muted hover:text-fg-dim"
            >
              Dismiss this action
            </button>
          </div>
        )}
        {action.status === "dismissed" && (
          <button
            onClick={() => onStatusChange(action, "pending")}
            className="text-[11.5px] text-accent hover:opacity-90"
          >
            Restore to pending
          </button>
        )}
      </div>

      {expanding && (
        <div className="absolute top-3 right-14 flex items-center gap-1 text-[11px] text-muted">
          <Loader2 size={11} className="animate-spin" /> generating guide…
        </div>
      )}
    </Sheet>
  );
}

function VariantTabs({
  count,
  chosen,
  onPick,
}: {
  count: number;
  chosen: number;
  onPick: (i: number) => void;
}) {
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[10.5px] uppercase tracking-[0.16em] text-muted font-medium">
          Variants
        </span>
        <span className="text-[10.5px] text-muted font-mono">
          A / B {count > 2 ? "/ C" : ""}
        </span>
        <div className="flex-1" />
        <span className="text-[10.5px] text-muted font-mono">
          {chosen + 1} of {count}
        </span>
      </div>
      <div
        className="inline-flex p-0.5 rounded-lg border bg-surface"
        style={{ borderColor: "var(--border-strong)" }}
      >
        {Array.from({ length: count }).map((_, i) => (
          <button
            key={i}
            onClick={() => onPick(i)}
            className="px-3 py-1 rounded-md text-[12px] font-medium transition-colors btn-press"
            style={{
              background:
                i === chosen ? "var(--accent-soft)" : "transparent",
              color: i === chosen ? "var(--accent)" : "var(--muted-strong)",
              borderColor: i === chosen ? "var(--accent-strong)" : "transparent",
            }}
            aria-pressed={i === chosen}
          >
            Variant {String.fromCharCode(65 + i)}
          </button>
        ))}
      </div>
    </div>
  );
}
