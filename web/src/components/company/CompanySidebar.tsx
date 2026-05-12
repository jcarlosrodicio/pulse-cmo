"use client";

import { useState } from "react";
import {
  Building2,
  Edit3,
  FileText,
  Compass,
  BookOpen,
  Mic2,
  ScanSearch,
  X,
  Plus,
  ChevronRight,
  Check,
  Loader2,
  Users,
  AtSign,
  Link2,
  Tag,
  Info,
} from "lucide-react";
import type { Action, DocumentKind, Project } from "@/lib/api";
import { Badge } from "../ui/Badge";
import { Skeleton, SkeletonText } from "../ui/Skeleton";

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[10.5px] uppercase tracking-[0.14em] text-muted font-medium px-4 mb-2">
      {children}
    </h3>
  );
}

const DOCS: { id: DocumentKind | "articles"; label: string; icon: typeof FileText }[] = [
  { id: "product_information", label: "Product Information", icon: FileText },
  { id: "competitor_analysis", label: "Competitor Analysis", icon: ScanSearch },
  { id: "brand_voice", label: "Brand Voice", icon: Mic2 },
  { id: "marketing_strategy", label: "Marketing Strategy", icon: Compass },
  { id: "articles", label: "Articles", icon: BookOpen },
];

export function CompanySidebar({
  project,
  actions,
  onOpenAction,
  onOpenDocument,
  onSaveProject,
  isInitialDive = false,
}: {
  project: Project;
  actions: Action[];
  onOpenAction: (a: Action) => void;
  onOpenDocument: (kind: DocumentKind) => void;
  onSaveProject: (patch: Partial<Project>) => Promise<void>;
  isInitialDive?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const strategyActions = actions.filter((a) => a.action_type === "strategy");
  const articleActions = actions.filter((a) => a.action_type === "article");

  return (
    <div className="h-full py-4 flex flex-col gap-5">
      {/* identity */}
      <div className="px-4">
        <div className="flex items-start gap-2.5">
          <div
            className="w-7 h-7 rounded-md flex items-center justify-center shrink-0"
            style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
          >
            <Building2 size={14} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <h2 className="font-semibold text-[14px] truncate" style={{ color: "var(--accent)" }}>
                {project.name}
              </h2>
              <button
                onClick={() => setEditing((v) => !v)}
                className="p-0.5 rounded text-muted hover:text-fg btn-press"
                aria-label="edit"
              >
                <Edit3 size={11} />
              </button>
            </div>
            <a
              href={project.url}
              target="_blank"
              rel="noreferrer"
              className="text-[11.5px] text-muted font-mono truncate block hover:text-fg-dim"
            >
              {project.url.replace(/^https?:\/\//, "")}
            </a>
          </div>
        </div>

        {editing ? (
          <InlineCompanyEditor
            project={project}
            onCancel={() => setEditing(false)}
            onSave={async (patch) => {
              await onSaveProject(patch);
              setEditing(false);
            }}
          />
        ) : project.description ? (
          <p
            onClick={() => setEditing(true)}
            className="mt-3 text-[12.5px] text-fg-dim leading-[1.55] cursor-text rounded-md p-1 -m-1 hover:bg-white/3 transition-colors line-clamp-4"
          >
            {project.description}
          </p>
        ) : isInitialDive ? (
          <div className="mt-3">
            <SkeletonText lines={3} />
          </div>
        ) : (
          <p
            onClick={() => setEditing(true)}
            className="mt-3 text-[12.5px] text-muted italic leading-[1.55] cursor-text rounded-md p-1 -m-1 hover:bg-white/3 transition-colors"
          >
            Add a short description for the agent…
          </p>
        )}
      </div>

      <Divider />

      {/* documents */}
      <div>
        <SectionHeader>Documents</SectionHeader>
        <ul className="px-2">
          {DOCS.map((doc) => {
            const Icon = doc.icon;
            const isAction = doc.id === "articles";
            const hasNew =
              (doc.id === "marketing_strategy" &&
                strategyActions.some((a) => a.status === "pending")) ||
              (doc.id === "articles" &&
                articleActions.some((a) => a.status === "pending"));
            return (
              <li key={doc.id}>
                <button
                  onClick={() => {
                    if (isAction) {
                      if (articleActions[0]) onOpenAction(articleActions[0]);
                    } else {
                      onOpenDocument(doc.id as DocumentKind);
                    }
                  }}
                  className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-md text-[12.5px] text-fg-dim hover:text-fg hover:bg-white/4 transition-colors group btn-press"
                >
                  <Icon size={13} className="text-muted shrink-0" />
                  <span className="flex-1 text-left truncate">{doc.label}</span>
                  {hasNew && <Badge tone="accent">New</Badge>}
                  <ChevronRight
                    size={11}
                    className="text-muted opacity-0 group-hover:opacity-100"
                  />
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <Divider />

      {/* competitors */}
      <div>
        <SectionHeader>Competitors</SectionHeader>
        <div className="px-3 flex flex-wrap gap-1.5">
          {project.competitors.length === 0 ? (
            isInitialDive ? (
              <>
                <Skeleton width={64} height={20} />
                <Skeleton width={88} height={20} />
                <Skeleton width={56} height={20} />
              </>
            ) : (
              <span className="text-muted text-[12px] px-1 italic">none yet</span>
            )
          ) : (
            project.competitors.map((c) => (
              <button
                key={c}
                onClick={() => setEditing(true)}
                className="group inline-flex items-center gap-1 px-2 py-1 rounded border bg-surface text-[11.5px] font-mono truncate max-w-full card-hover btn-press"
                style={{ borderColor: "var(--border)" }}
              >
                <span className="text-fg-dim">{c}</span>
                <X
                  size={9}
                  className="text-muted opacity-0 group-hover:opacity-100 transition-opacity"
                />
              </button>
            ))
          )}
          <button
            onClick={() => setEditing(true)}
            className="inline-flex items-center gap-1 px-2 py-1 rounded border border-dashed text-muted hover:text-fg-dim text-[11.5px] btn-press"
            style={{ borderColor: "var(--border)" }}
          >
            <Plus size={10} /> add
          </button>
        </div>
      </div>

      <Divider />

      {/* brand voice quick view */}
      {project.brand_voice ? (
        <div className="px-4">
          <SectionHeader>Voice</SectionHeader>
          <div className="text-[12.5px] text-fg-dim space-y-1">
            {project.brand_voice.tone && (
              <div>
                <span className="text-muted">tone </span>
                <span>{project.brand_voice.tone}</span>
              </div>
            )}
            {project.brand_voice.vocabulary && (
              <div>
                <span className="text-muted">vocab </span>
                <span className="line-clamp-2">{project.brand_voice.vocabulary}</span>
              </div>
            )}
          </div>
        </div>
      ) : isInitialDive ? (
        <div className="px-4">
          <SectionHeader>Voice</SectionHeader>
          <SkeletonText lines={2} />
        </div>
      ) : null}

      {/* schedule */}
      <div className="px-4 mt-auto">
        <SectionHeader>Schedule</SectionHeader>
        <div className="text-[12px] text-fg-dim flex items-center gap-2">
          <span className="font-mono tabular">
            {String(project.schedule_hour).padStart(2, "0")}:
            {String(project.schedule_minute).padStart(2, "0")}
          </span>
          <span className="text-muted">{project.timezone}</span>
          <span className="text-muted">·</span>
          <span className="text-muted">daily</span>
        </div>
      </div>
    </div>
  );
}

function Divider() {
  return <div className="mx-4" style={{ borderTop: "1px solid var(--border)" }} />;
}

function InlineCompanyEditor({
  project,
  onCancel,
  onSave,
}: {
  project: Project;
  onCancel: () => void;
  onSave: (patch: Partial<Project>) => Promise<void>;
}) {
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description || "");
  const [handle, setHandle] = useState(
    (project.writing_instructions as { handle?: string })?.handle || "",
  );
  const [companyUrl, setCompanyUrl] = useState(
    (project.writing_instructions as { company_url?: string })?.company_url || "",
  );
  const [team, setTeam] = useState(
    (project.writing_instructions as { team?: string })?.team || "",
  );
  const [category, setCategory] = useState(
    (project.writing_instructions as { category?: string })?.category || "",
  );
  const [competitorsText, setCompetitorsText] = useState(
    project.competitors.join(", "),
  );
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const wi = {
        ...(project.writing_instructions || {}),
        handle: handle || undefined,
        company_url: companyUrl || undefined,
        team: team || undefined,
        category: category || undefined,
      };
      const competitors = competitorsText
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      await onSave({
        name,
        description,
        competitors,
        writing_instructions: wi,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="mt-3 rounded-lg border bg-surface p-3 space-y-2.5"
      style={{ borderColor: "var(--border-strong)" }}
    >
      {/* name */}
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="project name"
        className="w-full bg-bg border rounded-md px-2.5 py-1.5 text-[13px] outline-none focus:border-accent"
        style={{ borderColor: "var(--border)" }}
      />

      {/* compact pill row */}
      <div className="flex flex-wrap gap-1.5">
        <PillInput
          icon={<Users size={11} />}
          placeholder="Team"
          value={team}
          onChange={setTeam}
        />
        <PillInput
          icon={<Tag size={11} />}
          placeholder="Category…"
          value={category}
          onChange={setCategory}
          dropdown
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        <PillInput
          icon={<AtSign size={11} />}
          placeholder="yourhandle"
          value={handle}
          onChange={setHandle}
        />
        <PillInput
          icon={<Link2 size={11} />}
          placeholder="profile or company URL"
          value={companyUrl}
          onChange={setCompanyUrl}
          helperIcon
        />
      </div>

      {companyUrl && (
        <div className="text-[10.5px] text-muted leading-snug flex items-start gap-1">
          <Info size={10} className="mt-0.5 shrink-0" />
          <span>Checks your last 10 public posts weekly to match your writing style.</span>
        </div>
      )}

      {/* description */}
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="What does this product do?"
        rows={6}
        className="w-full bg-bg border rounded-md p-2.5 text-[12.5px] leading-relaxed resize-y outline-none focus:border-accent"
        style={{ borderColor: "var(--border)" }}
      />

      {/* competitors */}
      <input
        value={competitorsText}
        onChange={(e) => setCompetitorsText(e.target.value)}
        placeholder="competitors (comma-separated)"
        className="w-full bg-bg border rounded-md px-2.5 py-1.5 text-[12px] font-mono outline-none focus:border-accent"
        style={{ borderColor: "var(--border)" }}
      />

      {/* footer */}
      <div className="flex items-center justify-end gap-2 pt-1">
        <button
          onClick={onCancel}
          className="px-2 py-1 rounded text-[12px] text-muted hover:text-fg btn-press"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1 rounded text-[12px] font-medium btn-press disabled:opacity-50"
          style={{
            background: "var(--accent)",
            color: "var(--accent-fg)",
          }}
        >
          {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
          Save
        </button>
      </div>
    </div>
  );
}

function PillInput({
  icon,
  placeholder,
  value,
  onChange,
  dropdown,
  helperIcon,
}: {
  icon: React.ReactNode;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  dropdown?: boolean;
  helperIcon?: boolean;
}) {
  return (
    <div
      className="flex items-center gap-1.5 px-2 py-1 rounded-full border bg-bg flex-1 min-w-0"
      style={{ borderColor: "var(--border)" }}
    >
      <span className="text-muted shrink-0">{icon}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="flex-1 min-w-0 bg-transparent text-[12px] outline-none placeholder:text-muted"
      />
      {helperIcon && <Info size={11} className="text-muted shrink-0" />}
      {dropdown && <ChevronRight size={11} className="text-muted shrink-0 rotate-90" />}
    </div>
  );
}
