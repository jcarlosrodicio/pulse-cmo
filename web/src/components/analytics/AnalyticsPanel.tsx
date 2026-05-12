"use client";

import { useState } from "react";
import { Activity, Link2, Wrench, Brain, CheckCircle2, Lock, Lightbulb } from "lucide-react";
import type { Project, PageSpeedStrategy } from "@/lib/api";
import { Gauge } from "../ui/Gauge";
import { Badge } from "../ui/Badge";
import { Skeleton, SkeletonText } from "../ui/Skeleton";

type Tab = "health" | "links" | "technical" | "geo" | "checks";

const TABS: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: "health", label: "Health", icon: Activity },
  { id: "links", label: "Links", icon: Link2 },
  { id: "technical", label: "Technical", icon: Wrench },
  { id: "geo", label: "AI / GEO", icon: Brain },
  { id: "checks", label: "Checks", icon: CheckCircle2 },
];

export function AnalyticsPanel({
  project,
  isInitialDive = false,
}: {
  project: Project;
  isInitialDive?: boolean;
}) {
  const [tab, setTab] = useState<Tab>("health");

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
        {tab === "links" && <PlaceholderTab title="Links analysis coming soon" subtitle="we'll show internal/external link health, broken links, and inbound mention tracking" />}
        {tab === "technical" && <TechnicalTab project={project} isInitialDive={isInitialDive} />}
        {tab === "geo" && <PlaceholderTab title="AI / GEO answer engines" subtitle="how your site is cited by ChatGPT, Claude, Perplexity, Gemini — coming soon" />}
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
      {!hasPagespeed && <ConnectServices />}

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

function ConnectServices() {
  return (
    <div
      className="rounded-xl border p-3 relative scanlines"
      style={{ borderColor: "var(--border)", background: "var(--surface)" }}
    >
      <div className="relative z-[1]">
        <div className="text-[10.5px] uppercase tracking-[0.14em] text-muted mb-2">
          Connect Google Services
        </div>
        <div className="grid grid-cols-2 gap-2">
          <ConnectCard name="Analytics" subtitle="Traffic & behavior" />
          <ConnectCard name="Search Console" subtitle="Search rankings" />
        </div>
      </div>
    </div>
  );
}

function ConnectCard({ name, subtitle }: { name: string; subtitle: string }) {
  return (
    <button
      className="text-left p-3 rounded-lg border bg-panel card-hover relative overflow-hidden group"
      style={{ borderColor: "var(--border)" }}
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="text-[12.5px] font-medium">{name}</div>
          <div className="text-[11px] text-muted">{subtitle}</div>
        </div>
        <Lock size={11} className="text-muted" />
      </div>
      <div className="text-[10.5px] uppercase tracking-wider font-medium text-accent opacity-80 group-hover:opacity-100">
        Connect →
      </div>
    </button>
  );
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
