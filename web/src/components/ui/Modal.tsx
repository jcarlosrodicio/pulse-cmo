"use client";

import { useEffect } from "react";
import { X } from "lucide-react";

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  maxWidth = "max-w-2xl",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidth?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8"
      style={{ background: "rgba(0,0,0,0.55)", backdropFilter: "blur(3px)" }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`modal-card w-full ${maxWidth} max-h-[90vh] flex flex-col rounded-xl border bg-surface`}
        style={{ borderColor: "var(--border-strong)" }}
      >
        <header
          className="flex items-center justify-between px-5 py-3.5 border-b shrink-0"
          style={{ borderColor: "var(--border)" }}
        >
          <h2 className="text-[14px] font-semibold tracking-tight">{title}</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-white/5 text-muted"
            aria-label="close"
          >
            <X size={15} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
        {footer && (
          <footer
            className="px-5 py-3 border-t shrink-0 flex items-center justify-end gap-2"
            style={{ borderColor: "var(--border)" }}
          >
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
