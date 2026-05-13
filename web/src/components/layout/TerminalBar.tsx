"use client";

import { useEffect, useRef } from "react";
import { ChevronUp, ChevronDown, Minimize2 } from "lucide-react";
import type { AgentEvent } from "@/lib/api";
import { stripReasoning } from "@/lib/text";

export type TerminalState = "collapsed" | "default" | "expanded";

type Line = {
  kind: "thought" | "tool" | "result" | "text" | "error" | "meta" | "user";
  text: string;
};

const HEIGHT: Record<TerminalState, number> = {
  collapsed: 28,
  default: 110,
  expanded: 280,
};

function eventsToLines(events: AgentEvent[]): Line[] {
  const lines: Line[] = [];
  let collecting = "";
  for (const ev of events) {
    // synthetic console events use a custom shape — see useSyntheticConsole
    if ((ev as { _synthetic?: true })._synthetic) {
      const syn = ev as unknown as { kind: Line["kind"]; text: string };
      lines.push({ kind: syn.kind, text: syn.text });
      continue;
    }
    if (ev.type === "start") {
      lines.push({ kind: "meta", text: "agent starting…" });
    } else if (ev.type === "iteration") {
      if (collecting) {
        lines.push({ kind: "text", text: collecting.trim() });
        collecting = "";
      }
    } else if (ev.type === "text") {
      collecting += ev.text;
    } else if (ev.type === "tool_call") {
      if (collecting) {
        lines.push({ kind: "thought", text: collecting.trim() });
        collecting = "";
      }
      const human = humanizeTool(ev.name, ev.arguments);
      if (human) lines.push({ kind: "tool", text: human });
    } else if (ev.type === "tool_result") {
      const human = humanizeResult(ev.name, ev.result);
      if (human) lines.push({ kind: "result", text: human });
    } else if (ev.type === "done") {
      if (collecting) {
        const cleaned = stripReasoning(collecting);
        if (cleaned) lines.push({ kind: "text", text: cleaned });
        collecting = "";
      }
      lines.push({ kind: "meta", text: `done · ${ev.iterations} iterations` });
    } else if (ev.type === "_done") {
      const tokens = ev.total_tokens;
      const cost = ev.cost_usd;
      if (typeof tokens === "number" && tokens > 0) {
        const cents = typeof cost === "number" ? formatCost(cost) : "—";
        lines.push({
          kind: "result",
          text: `▣ ${formatTokens(tokens)} tokens · ${cents}`,
        });
      }
    } else if (ev.type === "error") {
      lines.push({ kind: "error", text: `error: ${ev.message}` });
    }
  }
  if (collecting) {
    const cleaned = stripReasoning(collecting);
    if (cleaned) lines.push({ kind: "text", text: cleaned });
  }
  return lines;
}

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return (n / 1_000_000).toFixed(2).replace(/\.00$/, "") + "M";
}

function formatCost(usd: number): string {
  if (usd < 0.01) return `${(usd * 100).toFixed(2)}¢`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

function humanizeTool(name: string, args: Record<string, unknown>): string | null {
  switch (name) {
    case "crawl_website":
      return `Crawling ${truncUrl(String(args.url))}…`;
    case "audit_seo":
      return `Auditing SEO on ${truncUrl(String(args.url))}…`;
    case "check_pagespeed":
      return `Running PageSpeed (${args.strategy || "mobile"})…`;
    case "web_search":
      return `Searching: ${String(args.query || "")}`;
    case "news_search":
      return `News search: ${String(args.query || "")}`;
    case "read_url":
      return `Reading ${truncUrl(String(args.url))}…`;
    case "analyze_competitor":
      return `Analyzing competitor: ${truncUrl(String(args.competitor_url))}`;
    case "find_hn_opportunities":
      return `Scanning Hacker News for opportunities…`;
    case "find_reddit_opportunities":
      return `Scanning Reddit for opportunities…`;
    case "extract_brand_voice":
      return `Extracting brand voice from samples…`;
    case "draft_tweet":
      return `Drafting tweet…`;
    case "draft_article":
      return `Drafting article…`;
    case "draft_hn_post":
      return `Drafting HN post…`;
    case "draft_linkedin_post":
      return `Drafting LinkedIn post…`;
    case "draft_reddit_reply":
      return `Drafting Reddit reply…`;
    case "generate_marketing_strategy":
      return `Generating ${args.timeframe_days || 30}-day strategy…`;
    case "generate_product_information":
      return `Generating product information doc…`;
    case "generate_competitor_analysis":
      return `Generating competitor analysis doc…`;
    case "identify_market_gaps":
      return `Looking for positioning gaps…`;
    case "update_project_info":
      return `Updating project info…`;
    case "log_seo_fix":
      return `Logging SEO fix: ${String(args.title || "")}`;
    case "log_hn_opportunity":
      return `Logged HN opportunity`;
    case "log_reddit_opportunity":
      return `Logged Reddit opportunity`;
    default:
      return `→ ${name}`;
  }
}

function humanizeResult(name: string, raw: string): string | null {
  try {
    const data = JSON.parse(raw);
    if (data.ok === false) return `✗ ${name} failed`;
    switch (name) {
      case "crawl_website":
        return `✓ ${data.pages_fetched || 0} pages fetched`;
      case "audit_seo":
        return `✓ SEO score: ${data.score}/100 · ${data.counts?.high || 0} high, ${data.counts?.medium || 0} medium`;
      case "check_pagespeed":
        return `✓ perf ${data.scores?.performance ?? "—"} · seo ${data.scores?.seo ?? "—"} · a11y ${data.scores?.accessibility ?? "—"}`;
      case "web_search":
      case "news_search":
        return null;
      case "find_hn_opportunities":
        return `✓ ${data.found || 0} HN matches`;
      case "find_reddit_opportunities":
        return `✓ ${data.found || 0} Reddit matches`;
      case "extract_brand_voice":
        return data.profile?.tone ? `✓ voice: ${data.profile.tone}` : "✓ voice extracted";
      case "draft_tweet":
      case "draft_article":
      case "draft_hn_post":
      case "draft_linkedin_post":
      case "draft_reddit_reply":
        return `✓ draft saved (action #${data.action_id})`;
      case "generate_marketing_strategy":
        return `✓ strategy saved (action #${data.action_id})`;
      case "generate_product_information":
      case "generate_competitor_analysis":
        return `✓ document saved (doc #${data.document_id})`;
      case "update_project_info":
        return `✓ updated: ${(data.updated || []).join(", ")}`;
      case "log_seo_fix":
      case "log_hn_opportunity":
      case "log_reddit_opportunity":
        return `✓ logged (action #${data.action_id})`;
      case "identify_market_gaps":
        return `✓ ${data.gaps_found || 0} gaps identified`;
      default:
        return null;
    }
  } catch {
    return null;
  }
}

function truncUrl(url: string): string {
  return url.replace(/^https?:\/\//, "").replace(/^www\./, "");
}

function clsForKind(k: Line["kind"]): string {
  return {
    thought: "ln-thought",
    tool: "ln-tool",
    result: "ln-result",
    text: "ln-text",
    error: "ln-error",
    meta: "ln-meta",
    user: "ln-user",
  }[k];
}

export function TerminalBar({
  events,
  isStreaming,
  state,
  setState,
}: {
  events: AgentEvent[];
  isStreaming: boolean;
  state: TerminalState;
  setState: (s: TerminalState) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const lines = eventsToLines(events);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events.length, state]);

  const lastLine = lines[lines.length - 1];

  return (
    <div
      className="terminal relative overflow-hidden rounded-lg border"
      style={{
        height: HEIGHT[state],
        borderColor: "var(--border-strong)",
      }}
    >
      {state === "collapsed" ? (
        <button
          onClick={() => setState("default")}
          className="absolute inset-0 flex items-center gap-2 px-3 text-left"
          title="expand terminal"
        >
          <span className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted">
            console
          </span>
          {isStreaming && (
            <span className="flex items-center gap-1 text-accent text-[10.5px]">
              <span className="pulse-dot" /> running
            </span>
          )}
          <span className={`text-[11px] truncate flex-1 ${lastLine ? clsForKind(lastLine.kind) : "text-muted"}`}>
            {lastLine ? lastLine.text : "idle"}
          </span>
          <ChevronUp size={11} className="text-muted shrink-0" />
        </button>
      ) : (
        <>
          <div ref={ref} className="term-scroll absolute inset-0 px-4 py-2.5 pr-9 overflow-y-auto">
            {lines.length === 0 ? (
              <div className="ln-meta">idle. press &quot;Run now&quot; to start a pass.</div>
            ) : (
              lines.map((l, i) => (
                <div key={i} className={clsForKind(l.kind)}>
                  <span className="text-muted/60 mr-1.5">›</span>
                  {l.text}
                  {i === lines.length - 1 && isStreaming && <span className="caret" />}
                </div>
              ))
            )}
          </div>
          <div className="absolute top-1 right-1 flex flex-col gap-0.5">
            <button
              onClick={() => setState(state === "expanded" ? "default" : "expanded")}
              className="p-1 rounded hover:bg-white/5 text-muted-strong btn-press"
              title={state === "expanded" ? "shrink terminal" : "expand terminal"}
            >
              {state === "expanded" ? <ChevronDown size={11} /> : <ChevronUp size={11} />}
            </button>
            <button
              onClick={() => setState("collapsed")}
              className="p-1 rounded hover:bg-white/5 text-muted-strong btn-press"
              title="collapse"
            >
              <Minimize2 size={10} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
