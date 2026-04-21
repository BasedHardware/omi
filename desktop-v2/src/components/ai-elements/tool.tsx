"use client";

import { cn } from "@/lib/utils";
import {
  AlertCircleIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  WrenchIcon,
} from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";
import { useState } from "react";

export type ToolStatus = "running" | "completed" | "error";

export type ToolProps = HTMLAttributes<HTMLDivElement> & {
  name: string;
  status: ToolStatus;
  input?: string;
  output?: ReactNode;
  errorMessage?: string;
  defaultOpen?: boolean;
  /** Verb form shown while the tool is running, e.g. "Searching tasks". */
  runningLabel?: string;
};

const StatusIcon = ({ status }: { status: ToolStatus }) => {
  if (status === "running") {
    return (
      <span className="relative inline-flex size-3.5 shrink-0 items-center justify-center">
        <span className="size-3.5 animate-spin rounded-full border-2 border-muted-foreground/40 border-t-foreground" />
      </span>
    );
  }
  if (status === "error") {
    return <AlertCircleIcon className="size-3.5 shrink-0 text-destructive" />;
  }
  return <CheckCircle2Icon className="size-3.5 shrink-0 text-emerald-500" />;
};

export const Tool = ({
  name,
  status,
  input,
  output,
  errorMessage,
  defaultOpen = false,
  runningLabel,
  className,
  ...props
}: ToolProps) => {
  const [open, setOpen] = useState(defaultOpen);
  const hasBody = Boolean(input || output || errorMessage);
  const headerLabel =
    status === "running" ? `${runningLabel ?? `Running ${name}`}…` : name;

  return (
    <div
      className={cn(
        "my-2 w-full overflow-hidden rounded-lg border border-border bg-card/60",
        className,
      )}
      {...props}
    >
      <button
        type="button"
        onClick={() => hasBody && setOpen((o) => !o)}
        disabled={!hasBody}
        className={cn(
          "flex w-full items-center gap-2 px-3 py-2 text-left text-xs",
          hasBody && "hover:bg-secondary/50",
          !hasBody && "cursor-default",
        )}
        aria-expanded={open}
      >
        <StatusIcon status={status} />
        <WrenchIcon className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate font-medium text-foreground">
          {headerLabel}
        </span>
        {hasBody && (
          <ChevronDownIcon
            className={cn(
              "size-3.5 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-180",
            )}
          />
        )}
      </button>
      {open && hasBody && (
        <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground space-y-2">
          {input && (
            <div>
              <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/70">
                Input
              </div>
              <div className="text-foreground/80">{input}</div>
            </div>
          )}
          {output && (
            <div>
              <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/70">
                Output
              </div>
              <div className="text-foreground/80 whitespace-pre-wrap break-words">
                {output}
              </div>
            </div>
          )}
          {errorMessage && (
            <div>
              <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-destructive/80">
                Error
              </div>
              <div className="text-destructive">{errorMessage}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export type ToolGroupProps = HTMLAttributes<HTMLDivElement>;

export const ToolGroup = ({ className, ...props }: ToolGroupProps) => (
  <div
    className={cn("flex w-full flex-col gap-1", className)}
    {...props}
  />
);
