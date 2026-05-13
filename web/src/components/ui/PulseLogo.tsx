"use client";

/**
 * Pulse mark — a tiny round character whose smile is a heartbeat.
 *
 * Three layers, all `currentColor` so the mark inherits the parent's text
 * color (the header tints it accent, the chat bubble keeps it dim, the
 * sidebar uses fg-dim, etc.):
 *
 *   1. soft bean body — `opacity: 0.16`, gives a friendly silhouette halo
 *   2. two eye-ellipses — slightly tall for a wide-eyed feel
 *   3. a single-beat ECG line as the smile — the "pulse"
 *
 * Reads well from 11px (chat bubble) up to ~40px (onboarding hero).
 */
export function PulseLogo({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      {/* bean body — sits behind the face as a soft tinted halo */}
      <ellipse
        cx="12"
        cy="12.5"
        rx="9.6"
        ry="8.8"
        fill="currentColor"
        opacity="0.16"
      />
      {/* eyes — tall ellipses for a slightly wide-eyed friendliness */}
      <ellipse cx="9.1" cy="10.5" rx="1.05" ry="1.25" fill="currentColor" />
      <ellipse cx="14.9" cy="10.5" rx="1.05" ry="1.25" fill="currentColor" />
      {/* heartbeat smile — single ECG beat from left baseline to right baseline */}
      <path
        d="M6.5 15.4 L9.4 15.4 L10.3 13.6 L11.4 17 L12.7 12.2 L14 16 L14.7 14.4 L15.3 15.4 L17.5 15.4"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}
