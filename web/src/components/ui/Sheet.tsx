"use client";

import { useEffect } from "react";

export function Sheet({
  open,
  onClose,
  children,
  width = "max-w-[640px]",
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  width?: string;
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
    <>
      <div className="sheet-overlay" onClick={onClose} />
      <div className={`sheet-panel w-full ${width}`}>{children}</div>
    </>
  );
}
