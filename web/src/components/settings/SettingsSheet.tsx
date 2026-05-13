"use client";

import { useEffect, useState } from "react";
import {
  X,
  Save,
  Plus,
  Trash2,
  Loader2,
  RefreshCw,
  Eye,
  EyeOff,
  Check,
  AlertCircle,
  Plug,
  Star,
  Image as ImageIcon,
  Layers,
} from "lucide-react";
import { Sheet } from "../ui/Sheet";
import { useToast } from "../ui/Toast";
import {
  api,
  type ProviderConfig,
  type ProviderRole,
  type SettingsPayload,
} from "@/lib/api";

const ROLE_OPTIONS: { value: ProviderRole; label: string; icon: React.ReactNode; hint: string }[] = [
  { value: "primary", label: "Primary", icon: <Star size={11} />, hint: "First tried for every call" },
  { value: "secondary", label: "Secondary", icon: <Layers size={11} />, hint: "Failover when primary errors" },
  { value: "vision", label: "Vision", icon: <ImageIcon size={11} />, hint: "Used for image inputs" },
  { value: "fallback", label: "Fallback", icon: <Plug size={11} />, hint: "Last-resort failover" },
];

export function SettingsSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [settings, setSettings] = useState<SettingsPayload | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .getSettings()
      .then((data) => {
        setSettings(data);
        setProviders(data.providers);
      })
      .catch((e) => toast.push({ kind: "error", title: "Couldn't load settings", detail: String(e) }))
      .finally(() => setLoading(false));
  }, [open, toast]);

  function updateProvider(idx: number, patch: Partial<ProviderConfig>) {
    setProviders((prev) => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  }

  function removeProvider(idx: number) {
    setProviders((prev) => prev.filter((_, i) => i !== idx));
  }

  function addProvider() {
    setProviders((prev) => [
      ...prev,
      {
        name: `provider-${prev.length + 1}`,
        base_url: "https://api.openai.com/v1",
        api_key: null,
        api_key_env: null,
        model: "gpt-4o-mini",
        role: "fallback",
        timeout: 60,
        max_retries: 1,
        prompt_cost_per_million: 0,
        completion_cost_per_million: 0,
      },
    ]);
  }

  async function save() {
    setSaving(true);
    try {
      const res = await api.saveProviders(providers);
      setProviders(res.providers);
      toast.push({
        kind: "success",
        title: "Provider settings saved",
        detail: "Pulse will use the new config on the next call.",
      });
    } catch (e) {
      toast.push({ kind: "error", title: "Save failed", detail: String((e as Error).message) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet open={open} onClose={onClose} width="max-w-[760px]">
      <header
        className="flex items-center gap-2.5 px-5 py-3.5 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <Plug size={15} className="text-fg-dim" />
        <h2 className="text-[14px] font-semibold tracking-tight flex-1">
          Settings · Providers
        </h2>
        <button
          onClick={save}
          disabled={saving || loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded border text-[12px] font-medium disabled:opacity-50 btn-press"
          style={{
            borderColor: "var(--accent)",
            background: "var(--accent-soft)",
            color: "var(--accent)",
          }}
        >
          {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          onClick={onClose}
          className="p-1.5 rounded hover:bg-white/5 text-muted"
          aria-label="close"
        >
          <X size={15} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-5">
        <p className="text-[12px] text-muted mb-4 leading-relaxed">
          Configure your OpenAI-compatible providers. Set one as <strong className="text-fg">Primary</strong> —
          Pulse calls it first and only falls back if it errors. The vision role is reserved for image inputs.
        </p>

        {loading ? (
          <div className="space-y-3">
            <div className="h-24 shimmer w-full rounded-lg" />
            <div className="h-24 shimmer w-full rounded-lg" />
          </div>
        ) : (
          <>
            <div className="space-y-3 mb-4">
              {providers.map((p, idx) => (
                <ProviderCard
                  key={idx}
                  provider={p}
                  onChange={(patch) => updateProvider(idx, patch)}
                  onRemove={() => removeProvider(idx)}
                />
              ))}
            </div>
            <button
              onClick={addProvider}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-dashed text-[12.5px] text-muted-strong hover:text-fg hover:border-fg-dim/40 btn-press"
              style={{ borderColor: "var(--border-strong)" }}
            >
              <Plus size={12} /> Add provider
            </button>

            {settings && (
              <div className="mt-6 pt-4 text-[10.5px] text-muted font-mono"
                   style={{ borderTop: "1px solid var(--border)" }}>
                temperature {settings.default_temperature} · max iterations {settings.max_iterations}
              </div>
            )}
          </>
        )}
      </div>
    </Sheet>
  );
}

function ProviderCard({
  provider,
  onChange,
  onRemove,
}: {
  provider: ProviderConfig;
  onChange: (patch: Partial<ProviderConfig>) => void;
  onRemove: () => void;
}) {
  const toast = useToast();
  const [showKey, setShowKey] = useState(false);
  const [keyDraft, setKeyDraft] = useState(provider.api_key === "•••" ? "" : provider.api_key || "");
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [models, setModels] = useState<string[]>([]);

  useEffect(() => {
    // If the parent updates api_key (e.g. after save), reset draft. Skip
    // when value is the redacted sentinel — we leave the field empty so
    // the user can choose to enter a new key without erasing the saved one.
    if (provider.api_key && provider.api_key !== "•••") {
      setKeyDraft(provider.api_key);
    } else {
      setKeyDraft("");
    }
  }, [provider.api_key]);

  // sync the local draft up to the parent: empty means "leave unchanged"
  function setKey(value: string) {
    setKeyDraft(value);
    onChange({ api_key: value || (provider.api_key === "•••" ? "•••" : null) });
  }

  async function probe() {
    if (!provider.base_url) return;
    setProbing(true);
    setProbeResult(null);
    try {
      const apiKey = keyDraft || (provider.api_key === "•••" ? "" : "");
      // probe needs a real key — if user left it blank but a redacted key
      // exists server-side, just call save first.
      const result = await api.probeProvider(provider.base_url, apiKey);
      setProbeResult({
        ok: result.ok,
        msg: result.ok
          ? `connected · ${result.models ?? 0} models`
          : result.error || "failed",
      });
    } catch (e) {
      setProbeResult({ ok: false, msg: String((e as Error).message) });
    } finally {
      setProbing(false);
    }
  }

  async function loadModels() {
    if (!provider.base_url) return;
    setFetchingModels(true);
    try {
      const apiKey = keyDraft || "";
      const result = await api.fetchModels(provider.base_url, apiKey);
      if (result.ok && result.models) {
        setModels(result.models);
        toast.push({
          kind: "success",
          title: `Fetched ${result.models.length} models`,
          detail: provider.base_url,
        });
      } else {
        toast.push({ kind: "error", title: "Fetch failed", detail: result.error });
      }
    } finally {
      setFetchingModels(false);
    }
  }

  return (
    <div
      className="rounded-xl border bg-surface overflow-hidden"
      style={{ borderColor: "var(--border)" }}
    >
      <div
        className="flex items-center gap-2 px-3 py-2"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <RoleBadge role={provider.role} />
        <input
          value={provider.name}
          onChange={(e) => onChange({ name: e.target.value })}
          className="flex-1 bg-transparent border-0 outline-none text-[13px] font-medium"
          placeholder="provider name"
        />
        <button
          onClick={onRemove}
          className="p-1.5 rounded hover:bg-white/5 text-muted-strong btn-press"
          aria-label="remove"
          title="remove"
        >
          <Trash2 size={12} />
        </button>
      </div>

      <div className="p-3 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Role">
            <select
              value={provider.role}
              onChange={(e) => onChange({ role: e.target.value as ProviderRole })}
              className="w-full bg-surface border rounded-md px-2.5 py-1.5 text-[12.5px]"
              style={{ borderColor: "var(--border-strong)" }}
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Model">
            {models.length > 0 ? (
              <select
                value={provider.model}
                onChange={(e) => onChange({ model: e.target.value })}
                className="w-full bg-surface border rounded-md px-2.5 py-1.5 text-[12.5px] font-mono"
                style={{ borderColor: "var(--border-strong)" }}
              >
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            ) : (
              <input
                value={provider.model}
                onChange={(e) => onChange({ model: e.target.value })}
                placeholder="model-id"
                className="w-full bg-surface border rounded-md px-2.5 py-1.5 text-[12.5px] font-mono"
                style={{ borderColor: "var(--border-strong)" }}
              />
            )}
          </Field>
        </div>

        <Field label="Base URL">
          <input
            value={provider.base_url}
            onChange={(e) => onChange({ base_url: e.target.value })}
            placeholder="https://api.example.com/v1"
            className="w-full bg-surface border rounded-md px-2.5 py-1.5 text-[12.5px] font-mono"
            style={{ borderColor: "var(--border-strong)" }}
          />
        </Field>

        <Field label="API Key">
          <div className="relative">
            <input
              type={showKey ? "text" : "password"}
              value={keyDraft}
              onChange={(e) => setKey(e.target.value)}
              placeholder={provider.api_key === "•••" ? "•••••• (saved — leave blank to keep)" : "sk-…"}
              className="w-full bg-surface border rounded-md px-2.5 py-1.5 pr-9 text-[12.5px] font-mono"
              style={{ borderColor: "var(--border-strong)" }}
              autoComplete="off"
            />
            <button
              onClick={() => setShowKey((v) => !v)}
              type="button"
              className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-white/5 text-muted-strong"
              aria-label={showKey ? "hide" : "show"}
            >
              {showKey ? <EyeOff size={11} /> : <Eye size={11} />}
            </button>
          </div>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Prompt $/M tokens">
            <input
              type="number"
              step="0.01"
              value={provider.prompt_cost_per_million}
              onChange={(e) =>
                onChange({ prompt_cost_per_million: parseFloat(e.target.value) || 0 })
              }
              className="w-full bg-surface border rounded-md px-2.5 py-1.5 text-[12.5px] font-mono"
              style={{ borderColor: "var(--border-strong)" }}
            />
          </Field>
          <Field label="Completion $/M tokens">
            <input
              type="number"
              step="0.01"
              value={provider.completion_cost_per_million}
              onChange={(e) =>
                onChange({ completion_cost_per_million: parseFloat(e.target.value) || 0 })
              }
              className="w-full bg-surface border rounded-md px-2.5 py-1.5 text-[12.5px] font-mono"
              style={{ borderColor: "var(--border-strong)" }}
            />
          </Field>
        </div>

        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={probe}
            disabled={probing || !provider.base_url}
            className="flex items-center gap-1 px-2.5 py-1 rounded border text-[11.5px] btn-press hover:bg-white/4 disabled:opacity-50"
            style={{ borderColor: "var(--border-strong)" }}
          >
            {probing ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
            Test connection
          </button>
          <button
            onClick={loadModels}
            disabled={fetchingModels || !provider.base_url}
            className="flex items-center gap-1 px-2.5 py-1 rounded border text-[11.5px] btn-press hover:bg-white/4 disabled:opacity-50"
            style={{ borderColor: "var(--border-strong)" }}
          >
            {fetchingModels ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
            Fetch models
          </button>
          {probeResult && (
            <span
              className="flex items-center gap-1 text-[11px]"
              style={{ color: probeResult.ok ? "var(--accent)" : "var(--danger)" }}
            >
              {probeResult.ok ? <Check size={11} /> : <AlertCircle size={11} />}
              <span className="truncate max-w-[200px]">{probeResult.msg}</span>
            </span>
          )}
          {models.length > 0 && !probeResult && (
            <span className="text-[11px] text-muted font-mono">{models.length} models loaded</span>
          )}
        </div>
      </div>
    </div>
  );
}

function RoleBadge({ role }: { role: ProviderRole }) {
  const meta = ROLE_OPTIONS.find((r) => r.value === role) || ROLE_OPTIONS[3];
  const isPrimary = role === "primary";
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-[0.12em] font-medium font-mono"
      title={meta.hint}
      style={{
        background: isPrimary ? "var(--accent-soft)" : "var(--elevated)",
        color: isPrimary ? "var(--accent)" : "var(--fg-dim)",
        borderColor: isPrimary ? "var(--accent-strong)" : "var(--border)",
        border: "1px solid",
      }}
    >
      {meta.icon} {meta.label}
    </span>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10.5px] uppercase tracking-[0.14em] text-muted font-medium mb-1">
        {label}
      </label>
      {children}
    </div>
  );
}
