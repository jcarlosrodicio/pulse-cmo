"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Send,
  Plus,
  ChevronLeft,
  MessageSquare,
  Trash2,
  Sparkles,
  Loader2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type ChatMessageRow, type ChatSession } from "@/lib/api";
import { stripReasoning } from "@/lib/text";
import { PulseLogo } from "../ui/PulseLogo";

const SUGGESTIONS = [
  "draft a launch tweet",
  "what should I post on LinkedIn this week?",
  "find me a top-of-funnel article topic",
  "audit my homepage SEO",
];

export function ChatPanel({ projectId }: { projectId: number }) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageRow[]>([]);
  const [input, setInput] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [busy, setBusy] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stopRef = useRef<(() => void) | null>(null);

  const loadSessions = useCallback(async () => {
    const list = await api.listChatSessions(projectId);
    setSessions(list);
    if (list.length === 0 && activeId === null) {
      // lazy-create a starter session on first open
      const s = await api.createChatSession(projectId);
      setSessions([s]);
      setActiveId(s.id);
    } else if (activeId === null && list.length > 0) {
      setActiveId(list[0].id);
    }
  }, [projectId, activeId]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // load messages when session changes
  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    (async () => {
      try {
        const detail = await api.getChatSession(activeId);
        if (!cancelled) setMessages(detail.messages);
      } catch {
        // noop
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, streamingText]);

  async function newSession() {
    const s = await api.createChatSession(projectId);
    setSessions((prev) => [s, ...prev]);
    setActiveId(s.id);
    setMessages([]);
    setShowHistory(false);
  }

  async function deleteSession(id: number) {
    await api.deleteChatSession(id);
    const remaining = sessions.filter((s) => s.id !== id);
    setSessions(remaining);
    if (activeId === id) {
      if (remaining.length > 0) {
        setActiveId(remaining[0].id);
      } else {
        const s = await api.createChatSession(projectId);
        setSessions([s]);
        setActiveId(s.id);
        setMessages([]);
      }
    }
  }

  async function send(text: string) {
    if (!text.trim() || !activeId || busy) return;
    setBusy(true);
    setStreamingText("");
    setActiveTool(null);
    // optimistic local user message
    setMessages((m) => [
      ...m,
      {
        id: -Date.now(),
        session_id: activeId,
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
      },
    ]);
    setInput("");

    let buf = "";
    stopRef.current?.();
    stopRef.current = api.sendChatMessage(activeId, text, (ev) => {
      if (ev.type === "text") {
        buf += ev.text;
        setStreamingText(buf);
      } else if (ev.type === "tool_call") {
        setActiveTool(ev.name);
      } else if (ev.type === "tool_result") {
        setActiveTool(null);
      } else if (ev.type === "done") {
        const finalText = ev.content || buf;
        setMessages((m) => [
          ...m.filter((x) => x.id > 0),
          // refetch authoritative server copies
        ]);
        // refresh from server to get the persisted ids
        (async () => {
          try {
            const detail = await api.getChatSession(activeId);
            setMessages(detail.messages);
          } finally {
            setStreamingText("");
            setBusy(false);
            // refresh sessions list to pick up auto-title
            loadSessions();
            void finalText;
          }
        })();
      } else if (ev.type === "_done") {
        setBusy(false);
      } else if (ev.type === "error") {
        setMessages((m) => [
          ...m,
          {
            id: -Date.now() - 1,
            session_id: activeId,
            role: "assistant",
            content: `*error: ${ev.message}*`,
            created_at: new Date().toISOString(),
          },
        ]);
        setBusy(false);
        setStreamingText("");
      }
    });
  }

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId),
    [sessions, activeId],
  );

  if (showHistory) {
    return (
      <SessionList
        sessions={sessions}
        activeId={activeId}
        onSelect={(id) => {
          setActiveId(id);
          setShowHistory(false);
        }}
        onNew={newSession}
        onClose={() => setShowHistory(false)}
        onDelete={deleteSession}
      />
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* header */}
      <div
        className="px-4 lg:px-5 pt-4 pb-3 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span className="text-accent">
            <PulseLogo size={14} />
          </span>
          <h2 className="text-[13.5px] font-semibold tracking-tight">Talk to AI CMO</h2>
          <div className="flex-1" />
          <button
            onClick={() => setShowHistory(true)}
            className="flex items-center gap-1 px-1.5 py-1 rounded hover:bg-white/5 text-muted-strong text-[11.5px]"
            title="sessions"
          >
            <MessageSquare size={12} />
            <span className="font-mono tabular">{sessions.length}</span>
          </button>
          <button
            onClick={newSession}
            className="p-1 rounded hover:bg-white/5 text-muted-strong"
            title="new chat"
          >
            <Plus size={13} />
          </button>
        </div>
        <div className="text-[11px] text-muted truncate">
          {activeSession?.title || "New conversation"}
        </div>
      </div>

      {/* messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 lg:px-5 py-4 space-y-4">
        {messages.length === 0 && !streamingText ? (
          <ChatEmpty onPick={send} />
        ) : (
          <>
            {messages.map((m) => (
              <MessageBubble key={m.id} role={m.role} content={m.content} />
            ))}
            {streamingText && <MessageBubble role="assistant" content={streamingText} streaming />}
            {activeTool && (
              <div className="flex items-center gap-2 text-[11.5px] text-muted">
                <Loader2 size={11} className="animate-spin" />
                <span className="font-mono">{humanizeTool(activeTool)}</span>
              </div>
            )}
          </>
        )}
      </div>

      {/* composer */}
      <div className="px-3 lg:px-4 pb-4 pt-2 shrink-0">
        <Composer value={input} onChange={setInput} onSubmit={send} busy={busy} />
      </div>
    </div>
  );
}

function MessageBubble({
  role,
  content,
  streaming,
}: {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}) {
  const clean = role === "assistant" ? stripReasoning(content) : content;
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[85%] rounded-xl border bg-elevated px-3.5 py-2.5 text-[13px] whitespace-pre-wrap leading-relaxed"
          style={{ borderColor: "var(--border-strong)" }}
        >
          {content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2.5">
      <div
        className="w-6 h-6 rounded-md flex items-center justify-center shrink-0 mt-0.5"
        style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
      >
        <PulseLogo size={11} />
      </div>
      <div className="prose-pulse flex-1 min-w-0">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{clean || "…"}</ReactMarkdown>
        {streaming && <span className="caret" />}
      </div>
    </div>
  );
}

function Composer({
  value,
  onChange,
  onSubmit,
  busy,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (v: string) => void;
  busy: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [value]);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(value);
      }}
      className="rounded-xl border bg-surface focus-within:border-fg-dim/40 transition-colors"
      style={{ borderColor: "var(--border-strong)" }}
    >
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSubmit(value);
          }
        }}
        placeholder="Ask me anything…"
        rows={1}
        disabled={busy}
        className="w-full bg-transparent border-0 outline-none resize-none px-3 pt-2.5 pb-1 text-[13.5px] leading-relaxed"
      />
      <div className="flex items-center gap-1 px-2 pb-1.5">
        <div className="flex-1 text-[10.5px] text-muted px-1">
          <kbd className="font-mono px-1 py-0.5 rounded bg-white/4">⏎</kbd> send ·{" "}
          <kbd className="font-mono px-1 py-0.5 rounded bg-white/4">⇧⏎</kbd> newline
        </div>
        <button
          type="submit"
          disabled={!value.trim() || busy}
          className="p-1.5 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          style={{ color: "var(--accent)" }}
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
        </button>
      </div>
    </form>
  );
}

function ChatEmpty({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="h-full flex flex-col justify-center">
      <div className="text-center mb-5">
        <div
          className="w-10 h-10 rounded-xl mx-auto mb-3 flex items-center justify-center"
          style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
        >
          <Sparkles size={16} />
        </div>
        <div className="text-[14px] font-medium mb-1">Your full-time CMO</div>
        <div className="text-[12px] text-muted">
          Strategy, drafts, audits — ask anything.
        </div>
      </div>
      <div className="space-y-1.5">
        {SUGGESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onPick(q)}
            className="w-full text-left px-3 py-2 rounded border bg-surface card-hover text-[12.5px] text-fg-dim"
            style={{ borderColor: "var(--border)" }}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function SessionList({
  sessions,
  activeId,
  onSelect,
  onNew,
  onClose,
  onDelete,
}: {
  sessions: ChatSession[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onNew: () => void;
  onClose: () => void;
  onDelete: (id: number) => void;
}) {
  return (
    <div className="h-full flex flex-col">
      <div
        className="flex items-center gap-2 px-4 lg:px-5 pt-4 pb-3 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-white/5 text-muted-strong"
        >
          <ChevronLeft size={14} />
        </button>
        <h2 className="text-[13.5px] font-semibold tracking-tight flex-1">Chat sessions</h2>
        <button
          onClick={onNew}
          className="flex items-center gap-1 px-2 py-1 rounded text-[11.5px] text-accent hover:bg-white/4"
        >
          <Plus size={11} /> New
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {sessions.length === 0 ? (
          <div className="text-center text-muted text-[12px] py-10">no sessions yet</div>
        ) : (
          <ul className="space-y-1">
            {sessions.map((s) => (
              <li key={s.id}>
                <div
                  onClick={() => onSelect(s.id)}
                  className={`group flex items-center gap-2 px-2.5 py-2 rounded-md cursor-pointer ${
                    s.id === activeId ? "bg-white/6" : "hover:bg-white/3"
                  }`}
                >
                  <MessageSquare size={11} className="text-muted shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-[12.5px] truncate">{s.title}</div>
                    <div className="text-[10.5px] text-muted">
                      {new Date(s.last_activity_at).toLocaleString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                      {s.message_count ? ` · ${s.message_count} msg` : ""}
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(s.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-white/5 text-muted-strong"
                    aria-label="delete"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function humanizeTool(name: string): string {
  const map: Record<string, string> = {
    crawl_website: "crawling…",
    audit_seo: "auditing seo…",
    web_search: "searching web…",
    news_search: "searching news…",
    read_url: "reading page…",
    find_hn_opportunities: "scanning HN…",
    draft_tweet: "drafting tweet…",
    draft_article: "drafting article…",
    draft_linkedin_post: "drafting linkedin…",
    draft_hn_post: "drafting HN post…",
    extract_brand_voice: "extracting voice…",
    generate_marketing_strategy: "writing strategy…",
    analyze_competitor: "analyzing competitor…",
    check_pagespeed: "running pagespeed…",
  };
  return map[name] || `${name}…`;
}
