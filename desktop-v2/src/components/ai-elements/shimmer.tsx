"use client";

import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export type ShimmerProps = HTMLAttributes<HTMLSpanElement> & {
  children?: React.ReactNode;
};

export const Shimmer = ({
  children = "Thinking",
  className,
  ...props
}: ShimmerProps) => (
  <span
    className={cn(
      "inline-flex items-center gap-1 text-sm font-medium",
      "bg-gradient-to-r from-muted-foreground/40 via-foreground to-muted-foreground/40",
      "bg-[length:200%_100%] bg-clip-text text-transparent",
      "animate-shimmer",
      className,
    )}
    {...props}
  >
    {children}
  </span>
);
