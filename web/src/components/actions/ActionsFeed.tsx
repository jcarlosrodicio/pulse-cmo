"use client";

import { useMemo, useState } from "react";
import {
  ChevronDown,
  RefreshCw,
  Inbox,
  CheckCircle2,
  X,
  Check,
  SlidersHorizontal,
  Trash2,
  Copy,
  Search,
} from "lucide-react";
import type { Action, ActionType } from "@/lib/api";
import { stripReasoning } from "@/lib/text";
import { ACTION_GROUPS, groupLabelFor, metaFor } from "@/lib/actionTypes";
import { useToast } from "../ui/Toast";
import { Badge } from "../ui/Badge";
import { ChannelIcon } from "../ui/ChannelIcon";
import { Skeleton } from "../ui/Skeleton";
import { EmptyState } from "../ui/EmptyState";

type Filter = "pending" | "shipped" | "dismissed" | "all";

export function ActionsFeed({
  actions,
  onSelect,
  onRefresh,
  onOpenInstructions,
  onStatusChange,
  isInitialDive = false,
  lastRunAt,
  nextRunAt,
  runStatus,
  lastRunCostUsd,
  lastRunTokens,
}: {
  actions: Action[];
  onSelect: (a: Action) => void;
  onRefresh: () => void;
  onOpenInstructions: () => void;
  onStatusChange?: (a: Action, status: Action["status"]) => void;
  isInitialDive?: boolean;
  lastRunAt?: string | null;
  nextRunAt?: string | null;
  runStatus?: "idle" | "running" | "done";
  lastRunCostUsd?: number | null;
  lastRunTokens?: number | null;
}) {
  const [filter, setFilter] = useState<Filter>("pending");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);

  const searched = useMemo(() => {
    if (!query.trim()) return actions;
    const q = query.toLowerCase();
    return actions.filter(
      (a) =>
        a.title.toLowerCase().includes(q) ||
        a.content.toLowerCase().includes(q),
    );
  }, [actions, query]);

  const filtered = useMemo(
    () =>
      filter === "all"
        ? searched
        : searched.filter((a) => a.status === filter),
    [searched, filter],
  );

  const counts = useMemo(
    () =>
      actions.reduce(
        (acc, a) => {
          acc[a.status] = (acc[a.status] || 0) + 1;
          acc.all++;
          return acc;
        },
        { pending: 0, shipped: 0, dismissed: 0, all: 0 } as Record<string, number>,
      ),
    [actions],
  );

  return (
    <div className="h-full flex flex-col">
      <div
        className="sticky top-0 z-10 bg-bg px-4 lg:px-5 pt-4 pb-3"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 mb-1">
          <h2 className="text-[13.5px] font-semibold tracking-tight">Actions Feed</h2>
          {counts.pending > 0 && (
            <Badge tone="accent">{counts.pending}</Badge>
          )}
          <div className="flex-1" />
          <button
            onClick={() => setShowSearch((v) => !v)}
            className={`p-1.5 rounded btn-press hover:bg-white/5 ${
              showSearch ? "text-fg" : "text-muted-strong"
            }`}
            aria-label="search"
            title="search (⌘/)"
          >
            <Search size={13} />
          </button>
          <button
            onClick={onOpenInstructions}
            className="p-1.5 rounded btn-press hover:bg-white/5 text-muted-strong"
            aria-label="writing instructions"
            title="writing instructions"
          >
            <SlidersHorizontal size={13} />
          </button>
          <button
            onClick={onRefresh}
            className="p-1.5 rounded btn-press hover:bg-white/5 text-muted-strong"
            aria-label="refresh"
          >
            <RefreshCw size={13} />
          </button>
        </div>

        <StatsStrip
          counts={counts}
          lastRunAt={lastRunAt}
          nextRunAt={nextRunAt}
          runStatus={runStatus}
          lastRunCostUsd={lastRunCostUsd}
          lastRunTokens={lastRunTokens}
        />

        {showSearch && (
          <div className="mb-2.5">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="search title or content…"
              className="w-full bg-surface border rounded-md px-2.5 py-1.5 text-[12px] outline-none focus:border-fg-dim/40"
              style={{ borderColor: "var(--border-strong)" }}
              autoFocus
            />
          </div>
        )}

        <FilterTabs filter={filter} setFilter={setFilter} counts={counts} />
      </div>

      <div className="flex-1 overflow-y-auto px-3 lg:px-4 py-3 space-y-2.5">
        {filtered.length === 0 && isInitialDive ? (
          <ActionsSkeleton />
        ) : filtered.length === 0 ? (
          <FilteredEmpty filter={filter} hasQuery={!!query} />
        ) : (
          ACTION_GROUPS.map((g) => {
            const groupActions = filtered.filter((a) => g.types.includes(a.action_type));
            if (groupActions.length === 0) return null;
            return (
              <ActionGroup
                key={g.id}
                groupId={g.id}
                types={g.types}
                actions={groupActions}
                collapsed={collapsed[g.id]}
                onToggle={() => setCollapsed((c) => ({ ...c, [g.id]: !c[g.id] }))}
                onSelect={onSelect}
                onStatusChange={onStatusChange}
              />
            );
          })
        )}
      </div>
    </div>
  );
}

function StatsStrip({
  counts,
  lastRunAt,
  nextRunAt,
  runStatus,
  lastRunCostUsd,
  lastRunTokens,
}: {
  counts: Record<string, number>;
  lastRunAt?: string | null;
  nextRunAt?: string | null;
  runStatus?: "idle" | "running" | "done";
  lastRunCostUsd?: number | null;
  lastRunTokens?: number | null;
}) {
  const last = lastRunAt ? relTime(new Date(lastRunAt)) : null;
  const next = nextRunAt ? relTime(new Date(nextRunAt), { future: true }) : null;
  return (
    <div className="flex items-center gap-3 mb-2.5 text-[11px] text-muted-strong font-mono tabular flex-wrap">
      <Stat label="pending" value={counts.pending} tone="accent" />
      <Stat label="shipped" value={counts.shipped} />
      {runStatus === "running" ? (
        <span className="flex items-center gap-1 text-accent">
          <span className="pulse-dot" />
          running…
        </span>
      ) : last ? (
        <span>last run {last}</span>
      ) : null}
      {typeof lastRunCostUsd === "number" && lastRunCostUsd > 0 && (
        <span title={`${(lastRunTokens || 0).toLocaleString()} tokens`}>
          · {formatCostShort(lastRunCostUsd)}
        </span>
      )}
      {next && runStatus !== "running" && (
        <span className="text-muted">next {next}</span>
      )}
    </div>
  );
}

function formatCostShort(usd: number): string {
  if (usd < 0.01) return `${(usd * 100).toFixed(2)}¢`;
  if (usd < 1) return `$${usd.toFixed(3)}`;
  return `$${usd.toFixed(2)}`;
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "accent";
}) {
  return (
    <span className="flex items-baseline gap-1">
      <span
        className="font-medium"
        style={{ color: tone === "accent" ? "var(--accent)" : "var(--fg)" }}
      >
        {value}
      </span>
      <span className="text-muted">{label}</span>
    </span>
  );
}

function relTime(d: Date, opts: { future?: boolean } = {}): string {
  const diff = (d.getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  const sign = opts.future ? "in " : "";
  const suffix = opts.future ? "" : " ago";
  if (abs < 60) return opts.future ? "soon" : "just now";
  if (abs < 3600) return `${sign}${Math.floor(abs / 60)}m${suffix}`;
  if (abs < 86400) return `${sign}${Math.floor(abs / 3600)}h${suffix}`;
  return `${sign}${Math.floor(abs / 86400)}d${suffix}`;
}

function FilterTabs({
  filter,
  setFilter,
  counts,
}: {
  filter: Filter;
  setFilter: (f: Filter) => void;
  counts: Record<string, number>;
}) {
  return (
    <div className="flex gap-0.5">
      {(["pending", "shipped", "dismissed", "all"] as Filter[]).map((f) => {
        const active = f === filter;
        return (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-[11.5px] px-2.5 py-1 rounded capitalize font-medium transition-colors ${
              active
                ? "bg-white/8 text-fg"
                : "text-muted hover:text-fg hover:bg-white/4"
            }`}
          >
            {f}
            {counts[f] > 0 && (
              <span className="ml-1 text-muted font-mono tabular text-[10.5px]">
                {counts[f]}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function ActionGroup({
  groupId,
  types,
  actions,
  collapsed,
  onToggle,
  onSelect,
  onStatusChange,
}: {
  groupId: string;
  types: ActionType[];
  actions: Action[];
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (a: Action) => void;
  onStatusChange?: (a: Action, status: Action["status"]) => void;
}) {
  const hasNew = actions.some(
    (a) =>
      a.status === "pending" &&
      new Date(a.created_at).getTime() > Date.now() - 24 * 60 * 60 * 1000,
  );
  const groupLabel = groupLabelFor(types);
  void groupId;

  return (
    <div
      className="rounded-xl border bg-surface overflow-hidden"
      style={{ borderColor: "var(--border)" }}
    >
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-white/3 transition-colors btn-press"
      >
        <ChannelIcon kind={types[0]} size={22} />
        <div className="flex-1 min-w-0 text-left">
          <div className="text-[12px] uppercase tracking-[0.12em] text-muted font-medium">
            {groupLabel}
          </div>
          <div className="text-[12.5px] text-fg">
            {actions.length} item{actions.length === 1 ? "" : "s"} ready
          </div>
        </div>
        {hasNew && <Badge tone="accent">New</Badge>}
        <ChevronDown
          size={14}
          className="text-muted transition-transform"
          style={{ transform: collapsed ? "rotate(-90deg)" : "rotate(0deg)" }}
        />
      </button>

      {!collapsed && (
        <ul style={{ borderTop: "1px solid var(--border)" }}>
          {actions.map((a, idx) => (
            <ActionRow
              key={a.id}
              action={a}
              indexInGroup={idx}
              onClick={() => onSelect(a)}
              onStatusChange={onStatusChange}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ActionRow({
  action,
  indexInGroup,
  onClick,
  onStatusChange,
}: {
  action: Action;
  indexInGroup: number;
  onClick: () => void;
  onStatusChange?: (a: Action, status: Action["status"]) => void;
}) {
  const toast = useToast();
  const severity = (action.context as { severity?: string })?.severity;
  const meta = metaFor(action.action_type);
  const preview = stripReasoning(action.content)
    .replace(/[\n\r]+/g, " ")
    .slice(0, 120);

  const handleShip = (e: React.MouseEvent) => {
    e.stopPropagation();
    onStatusChange?.(action, "shipped");
    toast.push({
      kind: "success",
      title: "Marked as shipped",
      detail: action.title,
    });
  };

  const handleDismiss = (e: React.MouseEvent) => {
    e.stopPropagation();
    onStatusChange?.(action, "dismissed");
    toast.push({
      kind: "info",
      title: "Dismissed",
      detail: action.title,
      action: {
        label: "Undo",
        onClick: () => onStatusChange?.(action, "pending"),
      },
    });
  };

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(stripReasoning(action.content));
      toast.push({ kind: "success", title: "Copied to clipboard" });
    } catch {
      toast.push({ kind: "error", title: "Copy failed" });
    }
  };

  return (
    <li
      onClick={onClick}
      className="group relative cursor-pointer hover:bg-white/[0.025] transition-colors border-b last:border-b-0 row-rise"
      style={{
        borderColor: "var(--border)",
        animationDelay: `${Math.min(indexInGroup * 40, 280)}ms`,
      }}
    >
      {/* channel tint left border */}
      <span
        className="absolute left-0 top-0 bottom-0 w-[2px] opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: meta.tint }}
        aria-hidden="true"
      />

      <div className="px-3 py-2.5 flex items-start gap-2.5">
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-medium leading-snug line-clamp-2">{action.title}</div>
          <div className="text-[11.5px] text-muted mt-0.5 line-clamp-1">{preview}</div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {/* meta badges (visible by default) */}
          <div className="flex items-center gap-1 group-hover:opacity-0 transition-opacity">
            {severity && (
              <Badge
                tone={severity === "high" ? "danger" : severity === "medium" ? "warn" : "muted"}
              >
                {severity}
              </Badge>
            )}
            {action.status === "shipped" && <Badge tone="accent">Shipped</Badge>}
          </div>

          {/* hover-revealed quick actions */}
          <div
            className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-surface rounded-md px-1 py-0.5"
            style={{ borderColor: "var(--border)" }}
          >
            <QuickAction
              icon={<Copy size={11} />}
              label="copy content"
              onClick={handleCopy}
            />
            {action.status === "pending" && onStatusChange && (
              <>
                <QuickAction
                  icon={<Check size={12} />}
                  label="mark shipped"
                  onClick={handleShip}
                  tint="var(--accent)"
                />
                <QuickAction
                  icon={<Trash2 size={11} />}
                  label="dismiss"
                  onClick={handleDismiss}
                />
              </>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

function QuickAction({
  icon,
  label,
  onClick,
  tint,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: (e: React.MouseEvent) => void;
  tint?: string;
}) {
  return (
    <button
      onClick={onClick}
      className="p-1 rounded hover:bg-white/8 btn-press"
      title={label}
      aria-label={label}
      style={{ color: tint || "var(--fg-dim)" }}
    >
      {icon}
    </button>
  );
}

function ActionsSkeleton() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="rounded-xl border bg-surface p-3 row-rise"
          style={{ borderColor: "var(--border)", animationDelay: `${i * 60}ms` }}
        >
          <div className="flex items-center gap-2.5 mb-2">
            <Skeleton width={22} height={22} style={{ borderRadius: 6 }} />
            <div className="flex-1">
              <Skeleton width={90} height={9} className="mb-1.5" />
              <Skeleton width={140} height={10} />
            </div>
          </div>
          <Skeleton height={11} className="mt-2" />
          <Skeleton height={11} width="60%" className="mt-1" />
        </div>
      ))}
    </>
  );
}

function FilteredEmpty({
  filter,
  hasQuery,
}: {
  filter: Filter;
  hasQuery: boolean;
}) {
  if (hasQuery) {
    return (
      <EmptyState
        icon={<Search size={20} />}
        title="No matches"
        subtitle="Try a different keyword, or clear the search."
        hint="search · ⌘/ to focus"
      />
    );
  }
  if (filter === "shipped") {
    return (
      <EmptyState
        icon={<CheckCircle2 size={20} />}
        title="Nothing shipped yet"
        subtitle="Mark actions as complete after you post them — they'll land here as a trail."
      />
    );
  }
  if (filter === "dismissed") {
    return (
      <EmptyState
        icon={<X size={20} />}
        title="No dismissed items"
        subtitle="When you discard a draft, it shows up here so you can restore it."
      />
    );
  }
  return (
    <EmptyState
      icon={<Inbox size={20} />}
      title="No pending actions"
      subtitle="The agent didn't surface anything new on the last pass. Hit ‘Run now’ for another go."
      hint="run · g"
    />
  );
}
