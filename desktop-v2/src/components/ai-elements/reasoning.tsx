"use client";

import { cn } from "@/lib/utils";
import { BrainIcon, ChevronDownIcon } from "lucide-react";
import type { HTMLAttributes } from "react";
import { useEffect, useState } from "react";

export type ReasoningProps = HTMLAttributes<HTMLDivElement> & {
  text: string;
  isStreaming?: boolean;
  /** When true, auto-collapse once streaming ends. */
  autoCollapse?: boolean;
};

export const Reasoning = ({
  text,
  isStreaming = false,
  autoCollapse = true,
  className,
  ...props
}: ReasoningProps) => {
  const [open, setOpen] = useState(isStreaming);

  useEffect(() => {
    if (autoCollapse && !isStreaming) {
      setOpen(false);
    }
  }, [isStreaming, autoCollapse]);

  return (
    <div
      className={cn(
        "my-2 w-full overflow-hidden rounded-lg border border-border bg-muted/30",
        className,
      )}
      {...props}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-secondary/50"
        aria-expanded={open}
      >
        <BrainIcon className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate font-medium text-foreground">
          {isStreaming ? "Thinking…" : "Thought process"}
        </span>
        <ChevronDownIcon
          className={cn(
            "size-3.5 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2 text-xs italic text-muted-foreground whitespace-pre-wrap break-words">
          {text || (isStreaming ? "…" : "(no reasoning captured)")}
        </div>
      )}
    </div>
  );
};
