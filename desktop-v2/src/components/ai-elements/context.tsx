"use client";

import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export type ContextUsageProps = HTMLAttributes<HTMLDivElement> & {
  /** Used tokens / chars / whatever — same unit as `max`. */
  used: number;
  max: number;
  label?: string;
};

function formatCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export const ContextUsage = ({
  used,
  max,
  label = "Context",
  className,
  ...props
}: ContextUsageProps) => {
  const pct = Math.min(100, Math.max(0, (used / max) * 100));
  const color =
    pct >= 85
      ? "text-destructive"
      : pct >= 60
        ? "text-amber-500"
        : "text-muted-foreground";
  const barColor =
    pct >= 85
      ? "bg-destructive"
      : pct >= 60
        ? "bg-amber-500"
        : "bg-foreground/60";

  return (
    <div
      className={cn("flex items-center gap-2 text-xs", color, className)}
      title={`${formatCompact(used)} / ${formatCompact(max)} ${label.toLowerCase()}`}
      {...props}
    >
      <span className="hidden sm:inline">{label}</span>
      <div className="relative h-1.5 w-16 overflow-hidden rounded-full bg-secondary">
        <div
          className={cn("h-full transition-all", barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="tabular-nums">{Math.round(pct)}%</span>
    </div>
  );
};
