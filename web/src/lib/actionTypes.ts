/**
 * Single source of truth for every action type's metadata.
 *
 * Channel tints reference CSS variables (--ch-*) defined in app/tokens.css
 * so they adapt across light/dark themes automatically.
 */

import type { ActionType, TargetKind } from "./api";

export type ActionMeta = {
  // human-readable channel label (used in detail sheet titles)
  label: string;
  // short label shown inside the channel icon chip (1-3 chars)
  shortLabel: string;
  // group display name (used in the actions feed)
  groupLabel: string;
  // CSS color *variable* string for the channel tint
  tint: string;
  // CSS color *variable* string for the channel background tint
  tintBg: string;
  // whether the action body should render as markdown by default
  isMarkdown: boolean;
  // whether to auto-fetch the LLM-generated step-by-step detail on first open
  autoExpand: boolean;
  // whether the action carries a source URL (HN thread, Reddit thread, etc.)
  hasSourceUrl: boolean;
};

export const ACTION_TYPE_META: Record<ActionType, ActionMeta> = {
  seo_fix: {
    label: "SEO & GEO Recommendation",
    shortLabel: "SEO",
    groupLabel: "SEO & GEO",
    tint: "var(--ch-seo)",
    tintBg: "var(--ch-seo-bg)",
    isMarkdown: false,
    autoExpand: true,
    hasSourceUrl: false,
  },
  tweet: {
    label: "X Writer",
    shortLabel: "𝕏",
    groupLabel: "X Writer",
    tint: "var(--ch-tweet)",
    tintBg: "var(--ch-tweet-bg)",
    isMarkdown: false,
    autoExpand: false,
    hasSourceUrl: false,
  },
  hn_post: {
    label: "Hacker News Post",
    shortLabel: "Y",
    groupLabel: "Hacker News",
    tint: "var(--ch-hn)",
    tintBg: "var(--ch-hn-bg)",
    isMarkdown: false,
    autoExpand: false,
    hasSourceUrl: false,
  },
  hn_opportunity: {
    label: "Hacker News Opportunity",
    shortLabel: "Y",
    groupLabel: "Hacker News",
    tint: "var(--ch-hn)",
    tintBg: "var(--ch-hn-bg)",
    isMarkdown: true,
    autoExpand: true,
    hasSourceUrl: true,
  },
  reddit_opportunity: {
    label: "Reddit Opportunity",
    shortLabel: "r/",
    groupLabel: "Reddit",
    tint: "var(--ch-reddit)",
    tintBg: "var(--ch-reddit-bg)",
    isMarkdown: true,
    autoExpand: true,
    hasSourceUrl: true,
  },
  reddit_reply: {
    label: "Reddit Reply Draft",
    shortLabel: "r/",
    groupLabel: "Reddit",
    tint: "var(--ch-reddit)",
    tintBg: "var(--ch-reddit-bg)",
    isMarkdown: false,
    autoExpand: false,
    hasSourceUrl: true,
  },
  linkedin: {
    label: "LinkedIn Writer",
    shortLabel: "in",
    groupLabel: "LinkedIn Writer",
    tint: "var(--ch-linkedin)",
    tintBg: "var(--ch-linkedin-bg)",
    isMarkdown: false,
    autoExpand: false,
    hasSourceUrl: false,
  },
  article: {
    label: "Article",
    shortLabel: "¶",
    groupLabel: "Articles",
    tint: "var(--ch-article)",
    tintBg: "var(--ch-article-bg)",
    isMarkdown: true,
    autoExpand: false,
    hasSourceUrl: false,
  },
  market_gap: {
    label: "Positioning Gap",
    shortLabel: "△",
    groupLabel: "Positioning",
    tint: "var(--ch-gap)",
    tintBg: "var(--ch-gap-bg)",
    isMarkdown: true,
    autoExpand: true,
    hasSourceUrl: false,
  },
  strategy: {
    label: "Marketing Strategy",
    shortLabel: "S",
    groupLabel: "Strategy",
    tint: "var(--ch-strategy)",
    tintBg: "var(--ch-strategy-bg)",
    isMarkdown: true,
    autoExpand: false,
    hasSourceUrl: false,
  },
};

// Ordered group list as it should appear in the feed.
export const ACTION_GROUPS: { id: string; types: ActionType[] }[] = [
  { id: "seo", types: ["seo_fix"] },
  { id: "x", types: ["tweet"] },
  { id: "reddit", types: ["reddit_opportunity", "reddit_reply"] },
  { id: "articles", types: ["article"] },
  { id: "hn", types: ["hn_opportunity", "hn_post"] },
  { id: "linkedin", types: ["linkedin"] },
  { id: "positioning", types: ["market_gap"] },
  { id: "strategy", types: ["strategy"] },
];

export function metaFor(type: ActionType): ActionMeta {
  return ACTION_TYPE_META[type];
}

// Group label is derived from the first type's groupLabel — keeps the
// feed in sync if we add new sub-types under an existing group.
export function groupLabelFor(types: ActionType[]): string {
  return metaFor(types[0]).groupLabel;
}

export function groupTintFor(types: ActionType[]): string {
  return metaFor(types[0]).tint;
}

/**
 * Which targeted-run kind should fire when the user clicks "+ Generate" on
 * a given action group. Returns null for groups that can't be generated
 * standalone (none currently — but kept for future-proofing).
 */
export function targetForGroup(types: ActionType[]): TargetKind | null {
  const first = types[0];
  switch (first) {
    case "tweet":
      return "tweet";
    case "linkedin":
      return "linkedin";
    case "article":
      return "article";
    case "hn_post":
    case "hn_opportunity":
      // For HN, default to "find opportunities to comment on" since that's
      // higher value than crafting a Show HN cold. The user can override
      // by typing "show hn:" in the topic.
      return "hn_opportunity";
    case "reddit_reply":
    case "reddit_opportunity":
      return "reddit_reply";
    case "seo_fix":
      return "seo_audit";
    case "market_gap":
      return "market_gap";
    case "strategy":
      return "strategy";
    default:
      return null;
  }
}

/** Human-readable label for the topic prompt placeholder. */
export function topicPromptFor(target: TargetKind): string {
  return {
    tweet: "what's the tweet about? (optional)",
    linkedin: "what should the LinkedIn post cover? (optional)",
    hn_post: "show HN or ask HN topic (optional)",
    article: "article topic / target keyword",
    reddit_reply: "topic or niche (optional)",
    reddit_opportunity: "topic or niche (optional)",
    hn_opportunity: "keywords to search HN for (optional)",
    seo_audit: "(re-audits homepage — no topic needed)",
    competitor_scan: "competitor URL or name (optional)",
    market_gap: "(scans for gaps — no topic needed)",
    strategy: "(generates a 30-day strategy — no topic needed)",
  }[target];
}
