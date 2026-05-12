"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Check, AlertTriangle, Info, X } from "lucide-react";

export type ToastKind = "success" | "info" | "error";

export type Toast = {
  id: number;
  kind: ToastKind;
  title: string;
  detail?: string;
  action?: { label: string; onClick: () => void };
};

type ToastInput = Omit<Toast, "id">;

type ToastApi = {
  push: (t: ToastInput) => number;
  dismiss: (id: number) => void;
};

const Ctx = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

const TIMEOUT_MS = 4500;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counterRef = useRef(0);
  const timersRef = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timersRef.current[id];
    if (timer) {
      clearTimeout(timer);
      delete timersRef.current[id];
    }
  }, []);

  const push = useCallback(
    (t: ToastInput) => {
      counterRef.current += 1;
      const id = counterRef.current;
      setToasts((prev) => [...prev, { ...t, id }]);
      timersRef.current[id] = setTimeout(() => dismiss(id), TIMEOUT_MS);
      return id;
    },
    [dismiss],
  );

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      Object.values(timers).forEach(clearTimeout);
    };
  }, []);

  const value = useMemo(() => ({ push, dismiss }), [push, dismiss]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </Ctx.Provider>
  );
}

function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-[360px]">
      {toasts.map((t) => (
        <ToastCard key={t.id} toast={t} onDismiss={() => onDismiss(t.id)} />
      ))}
    </div>
  );
}

const ICONS: Record<ToastKind, typeof Check> = {
  success: Check,
  info: Info,
  error: AlertTriangle,
};

const COLORS: Record<ToastKind, { fg: string; bar: string }> = {
  success: { fg: "var(--accent)", bar: "var(--accent)" },
  info: { fg: "var(--info)", bar: "var(--info)" },
  error: { fg: "var(--danger)", bar: "var(--danger)" },
};

function ToastCard({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const Icon = ICONS[toast.kind];
  const c = COLORS[toast.kind];

  return (
    <div
      className="pointer-events-auto relative overflow-hidden rounded-lg border bg-surface shadow-lg"
      style={{
        borderColor: "var(--border-strong)",
        animation: "toast-in 240ms cubic-bezier(0.32, 0.72, 0, 1)",
      }}
    >
      <div
        className="absolute left-0 top-0 bottom-0 w-[3px]"
        style={{ background: c.bar }}
      />
      <div className="flex items-start gap-2.5 pl-4 pr-3 py-2.5">
        <Icon size={13} style={{ color: c.fg, marginTop: 2 }} />
        <div className="flex-1 min-w-0">
          <div className="text-[12.5px] font-medium text-fg">{toast.title}</div>
          {toast.detail && (
            <div className="text-[11.5px] text-muted-strong mt-0.5 line-clamp-2">
              {toast.detail}
            </div>
          )}
          {toast.action && (
            <button
              onClick={() => {
                toast.action!.onClick();
                onDismiss();
              }}
              className="mt-1.5 text-[11.5px] font-medium hover:opacity-90"
              style={{ color: c.fg }}
            >
              {toast.action.label} →
            </button>
          )}
        </div>
        <button
          onClick={onDismiss}
          className="p-0.5 rounded text-muted hover:text-fg-dim hover:bg-white/5"
          aria-label="dismiss"
        >
          <X size={11} />
        </button>
      </div>
      <div
        className="absolute bottom-0 left-0 h-[1px] opacity-50"
        style={{
          background: c.bar,
          animation: `toast-progress ${TIMEOUT_MS}ms linear forwards`,
        }}
      />
    </div>
  );
}
