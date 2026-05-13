"use client";

import type { ReactNode } from "react";

/**
 * Layout shell.
 *
 * The page is a vertical flex column: header at the top (sticky, but
 * grows/shrinks as the terminal changes state), main grid below taking the
 * remaining viewport via `flex-1 min-h-0`. The grid never uses a hardcoded
 * viewport calc — collapsing the terminal naturally reclaims that space.
 *
 *   ┌────────────────────────────────────┐
 *   │ Header (auto-height, sticky)       │
 *   ├────────────────────────────────────┤
 *   │                                    │
 *   │ Main grid — flex-1, min-h-0        │
 *   │  ┌─────┬─────┬─────┬─────┐         │
 *   │  │ sb  │ an  │ acts│ chat│ (lg)    │
 *   │  └─────┴─────┴─────┴─────┘         │
 *   │                                    │
 *   └────────────────────────────────────┘
 *
 * Each column is its own scroll container.
 */
export function Shell({
  sidebar,
  analytics,
  actions,
  chat,
  header,
  mobilePane,
  setMobilePane,
}: {
  sidebar: ReactNode;
  analytics: ReactNode;
  actions: ReactNode;
  chat: ReactNode;
  header: ReactNode;
  mobilePane: "company" | "analytics" | "actions" | "chat";
  setMobilePane: (p: "company" | "analytics" | "actions" | "chat") => void;
}) {
  return (
    <div className="flex flex-col h-[100dvh] overflow-hidden">
      {/* header — auto-height, doesn't scroll */}
      <div className="shrink-0">{header}</div>

      {/* main grid — fills remaining viewport */}
      <main
        className="flex-1 min-h-0 relative"
        style={{ background: "var(--border)" }}
      >
        {/* desktop: 4-column grid */}
        <div
          className="hidden lg:grid h-full"
          style={{
            gridTemplateColumns:
              "300px minmax(0, 1.05fr) minmax(0, 1fr) 360px",
            background: "var(--border)",
            gap: 1,
          }}
        >
          <ScrollPane>{sidebar}</ScrollPane>
          <ScrollPane>{analytics}</ScrollPane>
          <ScrollPane>{actions}</ScrollPane>
          <ScrollPane>{chat}</ScrollPane>
        </div>

        {/* tablet: 3 columns */}
        <div
          className="hidden md:grid lg:hidden h-full"
          style={{
            gridTemplateColumns:
              "minmax(0, 1fr) minmax(0, 1fr) 340px",
            background: "var(--border)",
            gap: 1,
          }}
        >
          <ScrollPane>{analytics}</ScrollPane>
          <ScrollPane>{actions}</ScrollPane>
          <ScrollPane>{chat}</ScrollPane>
        </div>

        {/* mobile: one pane at a time. Leave room for the fixed bottom nav. */}
        <div className="md:hidden h-full pb-14">
          <ScrollPane>
            {mobilePane === "company" && sidebar}
            {mobilePane === "analytics" && analytics}
            {mobilePane === "actions" && actions}
            {mobilePane === "chat" && chat}
          </ScrollPane>
        </div>
      </main>

      {/* mobile bottom nav */}
      <MobileBottomNav active={mobilePane} setActive={setMobilePane} />
    </div>
  );
}

function ScrollPane({ children }: { children: ReactNode }) {
  return (
    <div
      className="h-full min-h-0 overflow-y-auto"
      style={{
        background: "var(--bg)",
        scrollbarGutter: "stable",
      }}
    >
      {children}
    </div>
  );
}

function MobileBottomNav({
  active,
  setActive,
}: {
  active: string;
  setActive: (p: "company" | "analytics" | "actions" | "chat") => void;
}) {
  const items: { id: "company" | "analytics" | "actions" | "chat"; label: string; icon: string }[] = [
    { id: "company", label: "Brand", icon: "○" },
    { id: "analytics", label: "Site", icon: "◉" },
    { id: "actions", label: "Actions", icon: "▣" },
    { id: "chat", label: "Pulse", icon: "✷" },
  ];
  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-30 bottom-nav-blur grid grid-cols-4 shrink-0"
      style={{
        borderTop: "1px solid var(--border-strong)",
        background: "color-mix(in srgb, var(--bg) 88%, transparent)",
      }}
    >
      {items.map((it) => {
        const isActive = active === it.id;
        return (
          <button
            key={it.id}
            onClick={() => setActive(it.id)}
            className="flex flex-col items-center justify-center gap-0.5 py-2.5 transition-colors btn-press"
            style={{
              color: isActive ? "var(--accent)" : "var(--muted)",
            }}
          >
            <span className="font-mono text-[14px]">{it.icon}</span>
            <span className="text-[10px] uppercase tracking-wider font-medium">{it.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
