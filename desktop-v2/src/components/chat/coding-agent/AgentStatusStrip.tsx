/**
 * AgentStatusStrip — always-visible activity indicator for the coding-agent
 * surface. Sits between the conversation and the prompt input so the user
 * can always tell what the agent is doing (or that it's idle).
 *
 * Driven entirely by `AgentStatus` from `useCodingAgent`.
 */

import { Square, AlertCircle, CheckCircle2 } from "lucide-react";
import { Shimmer } from "../../ai-elements/shimmer";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AgentStatus } from "@/hooks/useCodingAgent";

interface Props {
  status: AgentStatus;
  onStop: () => void;
}

export function AgentStatusStrip({ status, onStop }: Props) {
  const stoppable =
    status.kind === "starting" ||
    status.kind === "thinking" ||
    status.kind === "running_tool" ||
    status.kind === "reviewing";

  return (
    <div
      className={cn(
        "shrink-0 flex items-center justify-between gap-3 px-5 h-9 border-t border-border",
        status.kind === "error"
          ? "bg-destructive/10 text-destructive"
          : "bg-muted/40 text-foreground",
      )}
      aria-live="polite"
      role="status"
    >
      <StatusContent status={status} />
      {stoppable && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onStop}
          className="h-6 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <Square className="size-3" />
          Stop
        </Button>
      )}
    </div>
  );
}

function StatusContent({ status }: { status: AgentStatus }) {
  switch (status.kind) {
    case "idle":
      return (
        <span className="text-xs text-muted-foreground">Ready · type a message to start</span>
      );

    case "starting":
      return <Shimmer className="text-xs">Starting agent…</Shimmer>;

    case "thinking":
      return <Shimmer className="text-xs">Thinking…</Shimmer>;

    case "running_tool":
      return (
        <div className="flex items-center gap-2 min-w-0">
          <Shimmer className="text-xs shrink-0">{verbForTool(status.tool)}</Shimmer>
          {status.preview && (
            <span className="text-xs font-mono text-muted-foreground truncate">
              {status.preview}
            </span>
          )}
        </div>
      );

    case "reviewing":
      return <Shimmer className="text-xs">Reviewing results…</Shimmer>;

    case "completed":
      return (
        <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 className="size-3.5" />
          <span>Done in {(status.durationMs / 1000).toFixed(1)}s</span>
        </div>
      );

    case "error":
      return (
        <div className="flex items-center gap-1.5 min-w-0 text-xs">
          <AlertCircle className="size-3.5 shrink-0" />
          <span className="truncate" title={status.message}>
            {status.message}
          </span>
        </div>
      );
  }
}

function verbForTool(tool: string): string {
  switch (tool) {
    case "read":
      return "Reading";
    case "write":
      return "Writing";
    case "edit":
      return "Editing";
    case "bash":
      return "Running command";
    case "dispatch_bash":
      return "Dispatching";
    case "grep":
      return "Searching";
    case "find":
      return "Finding";
    case "ls":
      return "Listing";
    case "td":
      return "Querying td";
    default:
      return `Running ${tool}`;
  }
}
