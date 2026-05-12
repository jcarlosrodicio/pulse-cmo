"use client";

import { useEffect, useState } from "react";
import { Save, Calendar, Plus, X } from "lucide-react";
import { Modal } from "../ui/Modal";
import { ChannelIcon } from "../ui/ChannelIcon";
import type { Project, WritingInstructions as WI } from "@/lib/api";

const REGIONS = [
  "Global (no filter)",
  "North America",
  "Europe",
  "Asia",
  "Latin America",
];

export function WritingInstructionsModal({
  open,
  onClose,
  project,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  project: Project;
  onSave: (wi: WI) => Promise<void>;
}) {
  const [wi, setWi] = useState<WI>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setWi(project.writing_instructions || {});
  }, [project.writing_instructions, open]);

  const save = async () => {
    setSaving(true);
    try {
      await onSave(wi);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Writing Instructions"
      footer={
        <>
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded text-[12px] text-muted hover:text-fg"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded border text-[12px] font-medium disabled:opacity-50"
            style={{
              borderColor: "var(--accent)",
              background: "var(--accent-soft)",
              color: "var(--accent)",
            }}
          >
            <Save size={12} /> {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <div className="space-y-6">
        {/* daily SEO fixes toggle */}
        <ToggleRow
          icon={<Calendar size={14} className="text-accent" />}
          title="Daily SEO fixes"
          subtitle="Receive at least one SEO recommendation per daily run"
          value={!!wi.daily_seo_fixes}
          onChange={(v) => setWi({ ...wi, daily_seo_fixes: v })}
        />

        <Divider />

        <ChannelBlock
          channel="hn"
          title="Hacker News"
          icon={<ChannelIcon kind="hn_opportunity" size={20} />}
        >
          <TextareaField
            value={wi.hn?.instructions || ""}
            onChange={(v) => setWi({ ...wi, hn: { ...wi.hn, instructions: v } })}
            placeholder="Example: technical detail first, no marketing language, lead with a concrete number or finding."
          />
          <ChipsField
            label="Search keywords"
            cap={10}
            values={wi.hn?.keywords || []}
            onChange={(arr) => setWi({ ...wi, hn: { ...wi.hn, keywords: arr } })}
          />
        </ChannelBlock>

        <ChannelBlock
          channel="x"
          title="X"
          icon={<ChannelIcon kind="tweet" size={20} />}
        >
          <TextareaField
            value={wi.x?.instructions || ""}
            onChange={(v) => setWi({ ...wi, x: { instructions: v } })}
            placeholder="Example: prioritize contrarian hooks, short lines, and a subtle CTA."
          />
        </ChannelBlock>

        <ChannelBlock
          channel="linkedin"
          title="LinkedIn"
          icon={<ChannelIcon kind="linkedin" size={20} />}
        >
          <TextareaField
            value={wi.linkedin?.instructions || ""}
            onChange={(v) => setWi({ ...wi, linkedin: { instructions: v } })}
            placeholder="Example: use founder voice, short paragraphs, no fluff, clear takeaway."
          />
        </ChannelBlock>

        <ChannelBlock
          channel="reddit"
          title="Reddit"
          icon={
            <div
              className="w-5 h-5 rounded-md flex items-center justify-center font-mono text-[10px] font-medium"
              style={{ background: "var(--ch-reddit-bg)", color: "var(--ch-reddit)" }}
            >
              r/
            </div>
          }
        >
          <TextareaField
            value={wi.reddit?.instructions || ""}
            onChange={(v) =>
              setWi({ ...wi, reddit: { ...wi.reddit, instructions: v } })
            }
            placeholder="Example: sound like a helpful user, keep replies concise, avoid over-promotional language."
          />
          <ChipsField
            label="Priority subreddits"
            cap={5}
            values={wi.reddit?.subreddits || []}
            onChange={(arr) =>
              setWi({ ...wi, reddit: { ...wi.reddit, subreddits: arr } })
            }
            prefix="r/"
          />
          <ChipsField
            label="Search keywords"
            cap={10}
            values={wi.reddit?.keywords || []}
            onChange={(arr) =>
              setWi({ ...wi, reddit: { ...wi.reddit, keywords: arr } })
            }
          />
          <SelectField
            label="Search region"
            value={wi.reddit?.region || REGIONS[0]}
            options={REGIONS}
            onChange={(v) => setWi({ ...wi, reddit: { ...wi.reddit, region: v } })}
          />
          <div className="text-[11px] text-muted">
            Reddit channel is read-only for MVP — drafts are copy-paste.
          </div>
        </ChannelBlock>
      </div>
    </Modal>
  );
}

function Divider() {
  return <div style={{ borderTop: "1px solid var(--border)" }} />;
}

function ToggleRow({
  icon,
  title,
  subtitle,
  value,
  onChange,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-8 h-8 rounded-md flex items-center justify-center" style={{ background: "var(--elevated)" }}>
        {icon}
      </div>
      <div className="flex-1">
        <div className="text-[13px] font-medium">{title}</div>
        <div className="text-[11.5px] text-muted">{subtitle}</div>
      </div>
      <button
        onClick={() => onChange(!value)}
        className="relative w-9 h-5 rounded-full transition-colors"
        style={{
          background: value ? "var(--accent)" : "rgba(255,255,255,0.10)",
        }}
        aria-pressed={value}
      >
        <span
          className="absolute top-0.5 w-4 h-4 rounded-full bg-bg transition-all"
          style={{ left: value ? 18 : 2 }}
        />
      </button>
    </div>
  );
}

function ChannelBlock({
  channel,
  title,
  icon,
  children,
}: {
  channel: string;
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  void channel;
  return (
    <div>
      <div className="flex items-center gap-2 mb-2.5">
        {icon}
        <h3 className="text-[13.5px] font-medium">{title}</h3>
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function TextareaField({
  value,
  onChange,
  placeholder,
  max = 4000,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  max?: number;
}) {
  return (
    <div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value.slice(0, max))}
        placeholder={placeholder}
        rows={3}
        className="w-full bg-surface border rounded-lg p-3 text-[13px] resize-y placeholder:text-muted"
        style={{ borderColor: "var(--border-strong)" }}
      />
      <div className="text-[10.5px] text-muted text-right mt-1 font-mono tabular">
        {value.length} / {max}
      </div>
    </div>
  );
}

function ChipsField({
  label,
  values,
  cap,
  onChange,
  prefix,
}: {
  label: string;
  values: string[];
  cap: number;
  onChange: (arr: string[]) => void;
  prefix?: string;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (!v) return;
    if (values.length >= cap) return;
    if (values.includes(v)) {
      setDraft("");
      return;
    }
    onChange([...values, v]);
    setDraft("");
  };
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <label className="text-[10.5px] uppercase tracking-[0.14em] text-muted font-medium">
          {label}
        </label>
        <span className="text-[10.5px] text-muted font-mono tabular">
          {values.length}/{cap}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {values.map((v, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded border bg-surface text-[12px] font-mono"
            style={{ borderColor: "var(--border-strong)" }}
          >
            {prefix}
            {v}
            <button
              onClick={() => onChange(values.filter((_, j) => j !== i))}
              className="text-muted hover:text-fg"
              aria-label="remove"
            >
              <X size={9} />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-1.5">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder="Add..."
          className="flex-1 bg-surface border rounded px-2.5 py-1 text-[12.5px]"
          style={{ borderColor: "var(--border)" }}
        />
        <button
          onClick={add}
          className="px-2 rounded border border-dashed text-muted hover:text-fg text-[12.5px]"
          style={{ borderColor: "var(--border-strong)" }}
        >
          <Plus size={11} /> Add
        </button>
      </div>
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="text-[10.5px] uppercase tracking-[0.14em] text-muted font-medium block mb-1.5">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-surface border rounded-lg px-3 py-2 text-[13px]"
        style={{ borderColor: "var(--border-strong)" }}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
