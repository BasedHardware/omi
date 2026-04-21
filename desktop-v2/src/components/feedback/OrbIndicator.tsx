import { memo } from "react";
import { cn } from "@/lib/utils";

export type PersonaState =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "asleep";

export type OrbVariant = "opal" | "halo" | "obsidian" | "command" | "glint" | "mana";

export type OrbSize = "xs" | "sm" | "md" | "lg" | "xl";

const sizeClass: Record<OrbSize, string> = {
  xs: "size-4",
  sm: "size-6",
  md: "size-10",
  lg: "size-20",
  xl: "size-40",
};

const dotSize: Record<OrbSize, string> = {
  xs: "size-1.5",
  sm: "size-2",
  md: "size-3",
  lg: "size-5",
  xl: "size-8",
};

export interface OrbIndicatorProps {
  state: PersonaState;
  /** Kept for API compatibility; ignored by the plain CSS indicator. */
  variant?: OrbVariant;
  size?: OrbSize;
  label?: string;
  sublabel?: string | null;
  layout?: "row" | "column";
  className?: string;
  orbClassName?: string;
}

// Plain CSS pulse dot. No Rive, no WebGL, no DOM reparenting.
export const OrbIndicator = memo(function OrbIndicator({
  state,
  size = "md",
  label,
  sublabel,
  layout = "row",
  className,
  orbClassName,
}: OrbIndicatorProps) {
  const color =
    state === "listening"
      ? "bg-green-500"
      : state === "speaking"
        ? "bg-blue-400"
        : state === "thinking"
          ? "bg-amber-400"
          : state === "idle"
            ? "bg-white/60"
            : "bg-white/20";
  const pulse =
    state === "listening" || state === "thinking" || state === "speaking"
      ? "animate-pulse"
      : "";

  const orb = (
    <div
      className={cn(
        "shrink-0 flex items-center justify-center",
        sizeClass[size],
        orbClassName,
      )}
      aria-hidden="true"
    >
      <div className={cn("rounded-full", dotSize[size], color, pulse)} />
    </div>
  );

  if (!label && !sublabel) {
    return <div className={cn("inline-flex items-center", className)}>{orb}</div>;
  }

  if (layout === "column") {
    return (
      <div className={cn("flex flex-col items-center gap-2 text-center", className)}>
        {orb}
        <div className="flex flex-col leading-tight">
          {label ? (
            <span className="text-sm font-medium text-foreground">{label}</span>
          ) : null}
          {sublabel ? (
            <span className="text-xs text-muted-foreground tabular-nums">
              {sublabel}
            </span>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className={cn("inline-flex items-center gap-2", className)}>
      {orb}
      <div className="flex min-w-0 flex-col leading-tight">
        {label ? (
          <span className="truncate text-[13px] font-medium text-foreground">
            {label}
          </span>
        ) : null}
        {sublabel ? (
          <span className="truncate text-[11px] text-muted-foreground tabular-nums">
            {sublabel}
          </span>
        ) : null}
      </div>
    </div>
  );
});
