"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Wrench,
  Brain,
  CheckCircle2,
  Lightbulb,
  Radar,
  RefreshCw,
  Loader2,
  ExternalLink,
  Sparkles,
  Link2,
  Check,
  AlertTriangle,
} from "lucide-react";
import {
  api,
  type Project,
  type PageSpeedStrategy,
  type TractionSummary,
  type TractionPlatform,
  type GeoSummary,
  type LinksSummary,
} from "@/lib/api";
import { Gauge } from "../ui/Gauge";
import { Badge } from "../ui/Badge";
import { Skeleton, SkeletonText } from "../ui/Skeleton";

type Tab = "health" | "traction" | "links" | "technical" | "geo" | "checks";

const TABS: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: "traction", label: "Traction", icon: Radar },
  { id: "health", label: "Health", icon: Activity },
  { id: "links", label: "Links", icon: Link2 },
  { id: "geo", label: "AI / GEO", icon: Brain },
  { id: "technical", label: "Technical", icon: Wrench },
  { id: "checks", label: "Checks", icon: CheckCircle2 },
];

export function AnalyticsPanel({
  project,
  isInitialDive = false,
}: {
  project: Project;
  isInitialDive?: boolean;
}) {
  const [tab, setTab] = useState<Tab>("traction");

  return (
    <div className="h-full flex flex-col">
      {/* tab bar */}
      <div
        className="sticky top-0 z-10 bg-bg px-4 lg:px-5 pt-4"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-1.5 mb-2.5">
          <h2 className="text-[13.5px] font-semibold tracking-tight">Site Analytics</h2>
          <span className="pulse-dot dim" />
        </div>
        <div className="flex gap-0.5 -mx-1 overflow-x-auto scrollbar-hidden">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = t.id === tab;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-t-md text-[12px] font-medium transition-colors whitespace-nowrap ${
                  active ? "text-fg" : "text-muted hover:text-fg-dim"
                }`}
                style={{
                  borderBottom: `2px solid ${active ? "var(--accent)" : "transparent"}`,
                }}
              >
                <Icon size={12} />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 lg:px-5 py-4 space-y-5">
        {tab === "health" && <HealthTab project={project} isInitialDive={isInitialDive} />}
        {tab === "traction" && <TractionTab project={project} />}
        {tab === "links" && <LinksTab project={project} />}
        {tab === "geo" && <GeoTab project={project} />}
        {tab === "technical" && <TechnicalTab project={project} isInitialDive={isInitialDive} />}
        {tab === "checks" && <ChecksTab project={project} isInitialDive={isInitialDive} />}
      </div>
    </div>
  );
}

function HealthTab({ project, isInitialDive }: { project: Project; isInitialDive: boolean }) {
  const ps = project.pagespeed_summary;
  const mobile = ps?.mobile;
  const desktop = ps?.desktop;
  const seo = project.seo_summary;
  const hasPagespeed = !!(mobile || desktop);

  if (!seo && !hasPagespeed && isInitialDive) {
    return <HealthSkeleton />;
  }

  return (
    <div className="space-y-5">
      {/* SEO posture quick read */}
      {seo && (
        <SectionCard
          title="On-Page SEO"
          subtitle="Latest audit snapshot"
          right={
            <div className="flex items-center gap-2">
              <span className="font-mono tabular text-[20px] font-medium" style={{ color: seo.score >= 80 ? "var(--accent)" : seo.score >= 50 ? "var(--warn)" : "var(--danger)" }}>
                {seo.score}
              </span>
              <span className="text-[11px] text-muted">/ 100</span>
            </div>
          }
        >
          <div className="grid grid-cols-3 gap-2 text-[12px]">
            <StatChip label="High" value={seo.counts.high} tone={seo.counts.high > 0 ? "danger" : "default"} />
            <StatChip label="Medium" value={seo.counts.medium} tone={seo.counts.medium > 0 ? "warn" : "default"} />
            <StatChip label="Low" value={seo.counts.low} tone="muted" />
          </div>
        </SectionCard>
      )}

      {/* PageSpeed */}
      {hasPagespeed && (
        <SectionCard
          title="PageSpeed Scores"
          subtitle="Lighthouse scores from Google"
        >
          {mobile && <PagespeedRow label="Mobile" data={mobile} />}
          {desktop && <PagespeedRow label="Desktop" data={desktop} />}
        </SectionCard>
      )}

      {/* Core Web Vitals */}
      {mobile?.core_web_vitals && (
        <SectionCard title="Core Web Vitals" subtitle="Lighthouse lab metrics (mobile)">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <CwvCell name="LCP" data={mobile.core_web_vitals.lcp} />
            <CwvCell name="FCP" data={mobile.core_web_vitals.fcp} />
            <CwvCell name="CLS" data={mobile.core_web_vitals.cls} />
            <CwvCell name="TBT" data={mobile.core_web_vitals.tbt} />
          </div>
        </SectionCard>
      )}

      {/* opportunities */}
      {mobile?.opportunities && mobile.opportunities.length > 0 && (
        <SectionCard title="Top Opportunities" subtitle="From PageSpeed Insights">
          <ul className="space-y-2">
            {mobile.opportunities.slice(0, 5).map((o) => (
              <li
                key={o.id}
                className="flex items-start gap-2 p-2 rounded border bg-surface"
                style={{ borderColor: "var(--border)" }}
              >
                <Lightbulb size={12} className="text-warn mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] font-medium">{o.title}</div>
                  <div className="text-[11.5px] text-muted line-clamp-2">{o.description}</div>
                </div>
                {o.savings_ms ? (
                  <Badge tone="warn">−{Math.round(o.savings_ms)}ms</Badge>
                ) : null}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {!seo && !hasPagespeed && <FirstDiveEmpty />}
    </div>
  );
}

function TechnicalTab({ project, isInitialDive }: { project: Project; isInitialDive: boolean }) {
  const seo = project.seo_summary;
  if (!seo) {
    if (isInitialDive) return <HealthSkeleton />;
    return <PlaceholderTab title="Run a first dive" subtitle="technical signals show up after the agent audits your site" />;
  }
  return (
    <div className="space-y-5">
      <SectionCard title="Site signals" subtitle="From audit_seo">
        <ul className="text-[12.5px] space-y-1.5">
          <SignalRow label="Sitemap" value={seo.summary.has_sitemap} />
          <SignalRow label="Structured data (JSON-LD)" value={seo.summary.has_jsonld} />
          <SignalRow label={`Images with alt text`} value={`${seo.summary.img_count - seo.summary.missing_alts}/${seo.summary.img_count}`} />
          <SignalRow label="H1 count" value={seo.summary.h1_count} />
        </ul>
      </SectionCard>

      <SectionCard title="Findings" subtitle={`${seo.findings.length} open`}>
        <ul className="space-y-2">
          {seo.findings.slice(0, 8).map((f, i) => (
            <li key={i} className="flex items-start gap-2.5 text-[12.5px]">
              <Badge
                tone={f.severity === "high" ? "danger" : f.severity === "medium" ? "warn" : "muted"}
                className="mt-0.5 shrink-0"
              >
                {f.severity}
              </Badge>
              <div className="flex-1">
                <div>{f.description}</div>
                <div className="text-muted text-[11.5px] mt-0.5">{f.fix}</div>
              </div>
            </li>
          ))}
        </ul>
      </SectionCard>
    </div>
  );
}

function ChecksTab({ project, isInitialDive }: { project: Project; isInitialDive: boolean }) {
  const seo = project.seo_summary;
  if (!seo) {
    if (isInitialDive) return <HealthSkeleton />;
    return <PlaceholderTab title="No checks yet" subtitle="run a first dive to populate" />;
  }
  return (
    <SectionCard title="Passed Checks" subtitle={`${seo.passed.length} passing`}>
      <ul className="space-y-1">
        {seo.passed.map((c, i) => (
          <li
            key={i}
            className="flex items-center gap-2 py-1.5 px-1 text-[12.5px] border-b"
            style={{ borderColor: "var(--border)" }}
          >
            <CheckCircle2 size={12} className="text-accent shrink-0" />
            <span className="flex-1">{c.check}</span>
            <span className="text-[11px] text-muted font-mono">{c.category}</span>
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

/* ── traction (digital footprint) ─────────────────────────────────── */

const PLATFORM_ICON: Record<string, string> = {
  reddit: "r/",
  hn: "Y",
  x: "𝕏",
  github: "▣",
  youtube: "▶",
  producthunt: "P",
  linkedin: "in",
  blog: "✎",
  directory: "≡",
  web: "◍",
};

const STRENGTH_TONE: Record<string, "accent" | "warn" | "muted"> = {
  strong: "accent",
  emerging: "warn",
  thin: "muted",
  none: "muted",
};

function TractionTab({ project }: { project: Project }) {
  const [traction, setTraction] = useState<TractionSummary | null>(project.traction_summary);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setTraction(project.traction_summary);
  }, [project.id, project.traction_summary]);

  const scanning = traction?.status === "scanning";

  const poll = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const { traction } = await api.getTraction(project.id);
        setTraction(traction);
        if (traction?.status !== "scanning" && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        /* keep polling */
      }
    }, 3000);
  }, [project.id]);

  useEffect(() => {
    if (scanning) poll();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [scanning, poll]);

  const scan = async () => {
    setTraction({ status: "scanning", started_at: new Date().toISOString() });
    try {
      await api.scanTraction(project.id);
      poll();
    } catch {
      setTraction({ status: "failed", error: "couldn't start scan" });
    }
  };

  // empty / first run
  if (!traction) {
    return (
      <div className="rounded-xl border border-dashed py-12 px-6 text-center bg-grid" style={{ borderColor: "var(--border-strong)" }}>
        <Radar size={22} className="mx-auto text-muted mb-2.5" />
        <div className="text-[13px] font-medium mb-1">Map your digital footprint</div>
        <div className="text-[12px] text-muted max-w-sm mx-auto mb-4">
          Pulse searches the web, Reddit, and Hacker News for {project.name} and shows where you&rsquo;re
          being talked about, where you&rsquo;re strong, and where to focus next.
        </div>
        <ScanButton scanning={false} onClick={scan} label="Scan footprint" />
      </div>
    );
  }

  if (traction.status === "scanning") {
    return (
      <div className="py-14 text-center">
        <Loader2 size={22} className="mx-auto animate-spin text-accent mb-3" />
        <div className="text-[13px] font-medium mb-1">Scanning the web…</div>
        <div className="text-[12px] text-muted">Searching Reddit, Hacker News, and the open web for mentions.</div>
      </div>
    );
  }

  if (traction.status === "failed") {
    return (
      <div className="py-12 text-center">
        <div className="text-[13px] text-danger mb-1">Scan failed</div>
        <div className="text-[12px] text-muted mb-4">{traction.error}</div>
        <ScanButton scanning={false} onClick={scan} label="Retry scan" />
      </div>
    );
  }

  const platforms = traction.platforms || [];
  const strongest = platforms.find((p) => p.key === traction.strongest);
  const sent = traction.sentiment || {};

  return (
    <div className="space-y-5">
      {/* header row */}
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <div className="text-[10.5px] uppercase tracking-[0.14em] text-muted">Digital footprint</div>
          <div className="text-[12px] text-muted-strong font-mono">
            {traction.totals?.mentions ?? 0} mentions · {traction.totals?.platforms ?? 0} platforms
            {traction.scanned_at ? ` · ${relScan(traction.scanned_at)}` : ""}
          </div>
        </div>
        <ScanButton scanning={false} onClick={scan} label="Rescan" small />
      </div>

      {/* summary tiles */}
      <div className="grid grid-cols-3 gap-2">
        <FootprintTile
          label="Strongest"
          value={strongest?.label || "—"}
          accent
        />
        <FootprintTile label="Mentions" value={String(traction.totals?.mentions ?? 0)} />
        <FootprintTile
          label="Sentiment"
          value={`${sent.positive ?? 0}+ / ${sent.negative ?? 0}−`}
        />
      </div>

      {/* insights */}
      {traction.insights && traction.insights.length > 0 && (
        <SectionCard title="Where to focus" subtitle="From your footprint">
          <ul className="space-y-2">
            {traction.insights.map((ins, i) => (
              <li key={i} className="flex items-start gap-2 text-[12.5px] text-fg-dim">
                <Sparkles size={12} className="text-accent mt-0.5 shrink-0" />
                {ins}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {/* per-platform */}
      <div className="space-y-3">
        {platforms.map((p) => (
          <PlatformCard key={p.key} platform={p} />
        ))}
      </div>
    </div>
  );
}

function PlatformCard({ platform }: { platform: TractionPlatform }) {
  const [open, setOpen] = useState(platform.strength === "strong");
  return (
    <div className="rounded-xl border bg-surface overflow-hidden" style={{ borderColor: "var(--border)" }}>
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-white/3 btn-press">
        <span
          className="w-7 h-7 rounded-md flex items-center justify-center text-[11px] font-mono font-medium shrink-0"
          style={{ background: "var(--elevated)", color: "var(--fg-dim)" }}
        >
          {PLATFORM_ICON[platform.key] || "◍"}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-medium">{platform.label}</span>
            <Badge tone={STRENGTH_TONE[platform.strength]}>{platform.strength}</Badge>
          </div>
          {platform.summary && <div className="text-[11.5px] text-muted line-clamp-1 mt-0.5">{platform.summary}</div>}
        </div>
        <span className="text-[11px] text-muted font-mono tabular shrink-0">{platform.count}</span>
      </button>
      {open && (
        <ul style={{ borderTop: "1px solid var(--border)" }}>
          {platform.mentions.map((m, i) => (
            <li key={i} className="px-3.5 py-2.5 border-b last:border-b-0" style={{ borderColor: "var(--border)" }}>
              <a
                href={m.url}
                target="_blank"
                rel="noreferrer"
                className="flex items-start gap-2 group"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] font-medium leading-snug line-clamp-2 group-hover:text-accent">{m.title || m.url}</div>
                  {m.snippet && <div className="text-[11.5px] text-muted line-clamp-2 mt-0.5">{m.snippet}</div>}
                  <div className="text-[10.5px] text-muted font-mono mt-1">
                    {m.extra ? `${m.extra}` : ""}{m.extra && m.date ? " · " : ""}{m.date ? shortDate(m.date) : ""}
                  </div>
                </div>
                <ExternalLink size={12} className="text-muted shrink-0 mt-0.5 opacity-0 group-hover:opacity-100" />
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ── AI / GEO ──────────────────────────────────────────────────────── */

function GeoTab({ project }: { project: Project }) {
  const [geo, setGeo] = useState<GeoSummary | null>(project.geo_summary);
  const [busy, setBusy] = useState(false);
  useEffect(() => setGeo(project.geo_summary), [project.id, project.geo_summary]);

  const scan = async () => {
    setBusy(true);
    try {
      const { geo } = await api.auditGeo(project.id);
      setGeo(geo);
    } finally {
      setBusy(false);
    }
  };

  if (!geo) {
    return (
      <ScanEmpty
        icon={<Brain size={22} />}
        title="AI answer-engine readiness"
        subtitle="Check whether ChatGPT, Claude, Perplexity and Gemini can crawl + cite your site, plus structured data and llms.txt."
        busy={busy}
        onScan={scan}
        label="Run GEO audit"
      />
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <div className="text-[10.5px] uppercase tracking-[0.14em] text-muted">GEO score</div>
          <div className="flex items-baseline gap-2">
            <span
              className="font-mono tabular text-[26px] font-medium"
              style={{ color: geo.score >= 80 ? "var(--accent)" : geo.score >= 50 ? "var(--warn)" : "var(--danger)" }}
            >
              {geo.score}
            </span>
            <span className="text-[11px] text-muted">/ 100</span>
          </div>
        </div>
        <ScanButton scanning={busy} onClick={scan} label="Rescan" small />
      </div>

      <SectionCard title="Answer-engine access" subtitle="Can these crawlers cite you?">
        <ul className="space-y-1.5">
          {geo.engines.map((e) => (
            <li key={e.engine} className="flex items-center gap-2 text-[12.5px]">
              {e.blocked ? (
                <AlertTriangle size={13} className="text-danger shrink-0" />
              ) : (
                <Check size={13} className="text-accent shrink-0" />
              )}
              <span className="flex-1">{e.engine}</span>
              <span className="text-[11px] font-mono" style={{ color: e.blocked ? "var(--danger)" : "var(--muted)" }}>
                {e.blocked ? "blocked" : "allowed"}
              </span>
            </li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard title="Signals" subtitle="What models look for">
        <ul className="text-[12.5px] space-y-1.5">
          <SignalRow label="llms.txt" value={geo.signals.has_llms_txt} />
          <SignalRow label="Structured data (JSON-LD)" value={geo.signals.has_jsonld} />
          <SignalRow label="FAQ / Q&A schema" value={geo.signals.has_faq_schema} />
          <SignalRow label="Meta description" value={geo.signals.has_meta_description} />
          <SignalRow label="Question-style headings" value={geo.signals.question_headings} />
          <SignalRow label="Headings on page" value={geo.signals.heading_count} />
        </ul>
      </SectionCard>

      {geo.findings.length > 0 && (
        <SectionCard title="Recommendations" subtitle={`${geo.findings.length} to improve`}>
          <ul className="space-y-2">
            {geo.findings.map((f, i) => (
              <li key={i} className="flex items-start gap-2.5 text-[12.5px]">
                <Badge tone={f.severity === "high" ? "danger" : f.severity === "medium" ? "warn" : "muted"} className="mt-0.5 shrink-0">
                  {f.severity}
                </Badge>
                <div className="flex-1">
                  <div>{f.description}</div>
                  <div className="text-muted text-[11.5px] mt-0.5">{f.fix}</div>
                </div>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  );
}

/* ── Links ─────────────────────────────────────────────────────────── */

function LinksTab({ project }: { project: Project }) {
  const [links, setLinks] = useState<LinksSummary | null>(project.links_summary);
  const [busy, setBusy] = useState(false);
  useEffect(() => setLinks(project.links_summary), [project.id, project.links_summary]);

  const scan = async () => {
    setBusy(true);
    try {
      const { links } = await api.auditLinks(project.id);
      setLinks(links);
    } finally {
      setBusy(false);
    }
  };

  if (!links) {
    return (
      <ScanEmpty
        icon={<Link2 size={22} />}
        title="Link health"
        subtitle="Count internal vs external links on your homepage and flag broken ones."
        busy={busy}
        onScan={scan}
        label="Scan links"
      />
    );
  }

  const c = links.counts;
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="text-[10.5px] uppercase tracking-[0.14em] text-muted">Link health</div>
        <ScanButton scanning={busy} onClick={scan} label="Rescan" small />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <StatChip label="Internal" value={c.internal} tone="default" />
        <StatChip label="External" value={c.external} tone="default" />
        <StatChip label="Broken" value={c.broken} tone={c.broken > 0 ? "danger" : "default"} />
      </div>
      <div className="text-[11.5px] text-muted">
        Checked {c.checked} external link{c.checked === 1 ? "" : "s"} for breakage.
      </div>

      {links.broken.length > 0 && (
        <SectionCard title="Broken links" subtitle={`${links.broken.length} need attention`}>
          <ul className="space-y-1.5">
            {links.broken.map((b, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px]">
                <AlertTriangle size={12} className="text-danger mt-0.5 shrink-0" />
                <a href={b.url} target="_blank" rel="noreferrer" className="flex-1 truncate hover:text-accent">
                  {b.url.replace(/^https?:\/\//, "")}
                </a>
                <span className="text-danger font-mono text-[11px]">{b.status}</span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {links.external_sample.length > 0 && (
        <SectionCard title="Outbound links" subtitle="Sample">
          <ul className="space-y-1">
            {links.external_sample.map((u, i) => (
              <li key={i} className="text-[12px] truncate">
                <a href={u} target="_blank" rel="noreferrer" className="text-fg-dim hover:text-accent">
                  {u.replace(/^https?:\/\//, "")}
                </a>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}
    </div>
  );
}

function ScanEmpty({
  icon,
  title,
  subtitle,
  busy,
  onScan,
  label,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  busy: boolean;
  onScan: () => void;
  label: string;
}) {
  return (
    <div className="rounded-xl border border-dashed py-12 px-6 text-center bg-grid" style={{ borderColor: "var(--border-strong)" }}>
      <div className="mx-auto text-muted mb-2.5 w-fit">{icon}</div>
      <div className="text-[13px] font-medium mb-1">{title}</div>
      <div className="text-[12px] text-muted max-w-sm mx-auto mb-4">{subtitle}</div>
      <ScanButton scanning={busy} onClick={onScan} label={label} />
    </div>
  );
}

function FootprintTile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-lg border bg-panel p-2.5" style={{ borderColor: "var(--border)" }}>
      <div className="text-[10px] uppercase tracking-wider text-muted mb-1">{label}</div>
      <div className="text-[14px] font-medium truncate" style={{ color: accent ? "var(--accent)" : "var(--fg)" }}>{value}</div>
    </div>
  );
}

function ScanButton({ scanning, onClick, label, small }: { scanning: boolean; onClick: () => void; label: string; small?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={scanning}
      className={`inline-flex items-center gap-1.5 rounded-lg border font-medium btn-press disabled:opacity-50 ${small ? "px-2.5 py-1 text-[11.5px]" : "px-3 py-1.5 text-[12.5px]"}`}
      style={{ borderColor: "var(--accent)", background: "var(--accent-soft)", color: "var(--accent)" }}
    >
      {scanning ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
      {label}
    </button>
  );
}

function relScan(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function shortDate(iso: string): string {
  try {
    const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
    if (isNaN(d.getTime())) return iso.slice(0, 10);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return iso;
  }
}

function SectionCard({
  title,
  subtitle,
  right,
  children,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-xl border bg-surface p-3.5 relative"
      style={{ borderColor: "var(--border)" }}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-[13px] font-medium">{title}</div>
          {subtitle && <div className="text-[11px] text-muted">{subtitle}</div>}
        </div>
        {right}
      </div>
      {children}
    </div>
  );
}

function PagespeedRow({ label, data }: { label: string; data: PageSpeedStrategy }) {
  return (
    <div className="mb-4 last:mb-0">
      <div className="text-[10.5px] uppercase tracking-[0.14em] text-muted mb-2.5">{label}</div>
      <div className="grid grid-cols-4 gap-2 relative">
        <Gauge value={data.scores.performance} label="Perf" />
        <Gauge value={data.scores.accessibility} label="A11y" />
        <Gauge value={data.scores.best_practices} label="Best" />
        <Gauge value={data.scores.seo} label="SEO" />
      </div>
    </div>
  );
}

function CwvCell({
  name,
  data,
}: {
  name: string;
  data: { display_value?: string; score?: number } | null | undefined;
}) {
  const score = data?.score;
  const tone = score == null ? "muted" : score >= 0.9 ? "accent" : score >= 0.5 ? "warn" : "danger";
  return (
    <div
      className="rounded-md border bg-panel p-2 text-center"
      style={{ borderColor: "var(--border)" }}
    >
      <div className="text-[10.5px] uppercase tracking-wider text-muted mb-1">{name}</div>
      <div className="font-mono tabular text-[14px]"
           style={{ color: tone === "accent" ? "var(--accent)" : tone === "warn" ? "var(--warn)" : tone === "danger" ? "var(--danger)" : "var(--fg)" }}>
        {data?.display_value ?? "—"}
      </div>
    </div>
  );
}

function StatChip({ label, value, tone }: { label: string; value: number; tone: "default" | "warn" | "danger" | "muted" }) {
  return (
    <div
      className="rounded-md border bg-panel p-2"
      style={{ borderColor: "var(--border)" }}
    >
      <div className="text-[10.5px] uppercase tracking-wider text-muted">{label}</div>
      <div className="font-mono tabular text-[16px] mt-0.5"
           style={{
             color: tone === "danger" ? "var(--danger)" : tone === "warn" ? "var(--warn)" : "var(--fg)",
           }}>
        {value}
      </div>
    </div>
  );
}

function SignalRow({ label, value }: { label: string; value: boolean | string | number }) {
  const ok = value === true || (typeof value === "string" && value !== "0/0") || (typeof value === "number" && value > 0);
  return (
    <li
      className="flex items-center gap-2 py-1 border-b"
      style={{ borderColor: "var(--border)" }}
    >
      <CheckCircle2 size={12} className={ok ? "text-accent" : "text-muted"} />
      <span className="flex-1">{label}</span>
      <span className="text-muted font-mono tabular">
        {typeof value === "boolean" ? (value ? "yes" : "no") : value}
      </span>
    </li>
  );
}

function FirstDiveEmpty() {
  return (
    <div
      className="rounded-xl border border-dashed py-10 px-6 text-center bg-grid"
      style={{ borderColor: "var(--border-strong)" }}
    >
      <div className="text-[13px] font-medium mb-1">No data yet</div>
      <div className="text-[12px] text-muted">Run your first dive to populate analytics</div>
    </div>
  );
}

function HealthSkeleton() {
  return (
    <div className="space-y-5">
      <div className="rounded-xl border bg-surface p-3.5" style={{ borderColor: "var(--border)" }}>
        <div className="flex items-center justify-between mb-3">
          <Skeleton width={120} height={12} />
          <Skeleton width={50} height={20} />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Skeleton height={48} />
          <Skeleton height={48} />
          <Skeleton height={48} />
        </div>
      </div>
      <div className="rounded-xl border bg-surface p-3.5" style={{ borderColor: "var(--border)" }}>
        <Skeleton width={140} height={12} className="mb-4" />
        <div className="grid grid-cols-4 gap-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex flex-col items-center gap-1.5">
              <Skeleton width={56} height={56} style={{ borderRadius: "50%" }} />
              <Skeleton width={32} height={9} />
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-xl border bg-surface p-3.5" style={{ borderColor: "var(--border)" }}>
        <Skeleton width={120} height={12} className="mb-3" />
        <SkeletonText lines={3} />
      </div>
    </div>
  );
}

function PlaceholderTab({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div
      className="rounded-xl border border-dashed py-12 text-center"
      style={{ borderColor: "var(--border-strong)" }}
    >
      <div className="text-[13px] font-medium mb-1">{title}</div>
      <div className="text-[12px] text-muted max-w-md mx-auto">{subtitle}</div>
    </div>
  );
}
