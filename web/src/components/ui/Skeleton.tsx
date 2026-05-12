"use client";

export function Skeleton({
  className = "",
  width = "100%",
  height = 14,
  style,
}: {
  className?: string;
  width?: string | number;
  height?: string | number;
  style?: React.CSSProperties;
}) {
  return (
    <span
      className={`shimmer block ${className}`}
      style={{ width, height, borderRadius: 4, ...style }}
      aria-hidden="true"
    />
  );
}

export function SkeletonText({
  lines = 3,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height={11}
          width={i === lines - 1 ? "60%" : "100%"}
        />
      ))}
    </div>
  );
}
