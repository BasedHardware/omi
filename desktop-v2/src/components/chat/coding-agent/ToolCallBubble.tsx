import { useState } from "react";
import {
  FileText,
  Folder,
  Search,
  FileEdit,
  FilePlus,
  Terminal,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface ToolCall {
  id: string;
  tool: string;
  input: unknown;
}

export interface ToolResult {
  output: string;
  isError: boolean;
}

interface Props {
  call: ToolCall;
  result?: ToolResult;
}

// ---------------------------------------------------------------------------
// Per-tool metadata
// ---------------------------------------------------------------------------

interface ToolMeta {
  Icon: React.ComponentType<{ className?: string }>;
  label: string;
  color: string;
}

function toolMeta(tool: string): ToolMeta {
  switch (tool) {
    case "read":
      return { Icon: FileText, label: "Read", color: "text-blue-400" };
    case "ls":
      return { Icon: Folder, label: "List", color: "text-yellow-400" };
    case "find":
      return { Icon: Search, label: "Find", color: "text-purple-400" };
    case "grep":
      return { Icon: Search, label: "Grep", color: "text-cyan-400" };
    case "edit":
      return { Icon: FileEdit, label: "Edit", color: "text-orange-400" };
    case "write":
      return { Icon: FilePlus, label: "Write", color: "text-green-400" };
    case "bash":
      return { Icon: Terminal, label: "Bash", color: "text-emerald-400" };
    default:
      return { Icon: Terminal, label: tool, color: "text-muted-foreground" };
  }
}

// ---------------------------------------------------------------------------
// Input summary helpers — extract the most useful string to display in the
// collapsed header so the user knows what path / command was used.
// ---------------------------------------------------------------------------

function summariseInput(tool: string, input: unknown): string {
  if (!input || typeof input !== "object") return String(input ?? "");
  const obj = input as Record<string, unknown>;
  switch (tool) {
    case "read":
    case "edit":
    case "write":
    case "ls":
      return typeof obj.path === "string" ? obj.path : JSON.stringify(input);
    case "find":
    case "grep":
      return typeof obj.pattern === "string"
        ? obj.pattern
        : typeof obj.path === "string"
          ? obj.path
          : JSON.stringify(input);
    case "bash":
      return typeof obj.command === "string" ? obj.command : JSON.stringify(input);
    default:
      return JSON.stringify(input);
  }
}

// ---------------------------------------------------------------------------
// Body renderers per tool kind
// ---------------------------------------------------------------------------

function ToolBody({ call, result }: { call: ToolCall; result?: ToolResult }) {
  const { tool, input } = call;
  const obj = (input && typeof input === "object" ? input : {}) as Record<string, unknown>;

  if (tool === "bash") {
    const command = typeof obj.command === "string" ? obj.command : JSON.stringify(input);
    return (
      <div className="space-y-2">
        <pre className="overflow-x-auto rounded-md bg-muted px-3 py-2 text-xs font-mono text-muted-foreground">
          <span className="select-none text-muted-foreground/50">$ </span>
          {command}
        </pre>
        {result && (
          <pre
            className={cn(
              "overflow-x-auto rounded-md px-3 py-2 text-xs font-mono",
              result.isError
                ? "bg-destructive/10 text-destructive"
                : "bg-muted text-foreground",
            )}
          >
            {result.output || "(no output)"}
          </pre>
        )}
      </div>
    );
  }

  if (tool === "edit" || tool === "write") {
    const path =
      typeof obj.path === "string" ? obj.path : typeof obj.file_path === "string" ? obj.file_path : "";
    const newContent =
      typeof obj.new_content === "string"
        ? obj.new_content
        : typeof obj.content === "string"
          ? obj.content
          : JSON.stringify(input, null, 2);
    return (
      <div className="space-y-1.5">
        {path && (
          <p className="text-xs text-muted-foreground font-mono">
            {tool === "edit" ? "Modified" : "Wrote"} {path}
          </p>
        )}
        <pre className="overflow-x-auto rounded-md bg-muted px-3 py-2 text-xs font-mono text-foreground max-h-48">
          {newContent}
        </pre>
        {result && result.isError && (
          <pre className="overflow-x-auto rounded-md bg-destructive/10 px-3 py-2 text-xs font-mono text-destructive">
            {result.output}
          </pre>
        )}
      </div>
    );
  }

  if (tool === "read" || tool === "ls" || tool === "find") {
    const path =
      typeof obj.path === "string"
        ? obj.path
        : typeof obj.directory === "string"
          ? obj.directory
          : JSON.stringify(input);
    return (
      <div className="space-y-1.5">
        <p className="text-xs font-mono text-muted-foreground">{path}</p>
        {result && (
          <pre
            className={cn(
              "overflow-x-auto rounded-md px-3 py-2 text-xs font-mono max-h-48",
              result.isError
                ? "bg-destructive/10 text-destructive"
                : "bg-muted text-foreground",
            )}
          >
            {result.output || "(empty)"}
          </pre>
        )}
      </div>
    );
  }

  if (tool === "grep") {
    const pattern = typeof obj.pattern === "string" ? obj.pattern : "";
    const path = typeof obj.path === "string" ? obj.path : "";
    return (
      <div className="space-y-1.5">
        {pattern && (
          <p className="text-xs font-mono text-muted-foreground">
            pattern: <span className="text-foreground">{pattern}</span>
            {path ? ` in ${path}` : ""}
          </p>
        )}
        {result && (
          <pre
            className={cn(
              "overflow-x-auto rounded-md px-3 py-2 text-xs font-mono max-h-48",
              result.isError
                ? "bg-destructive/10 text-destructive"
                : "bg-muted text-foreground",
            )}
          >
            {result.output || "(no matches)"}
          </pre>
        )}
      </div>
    );
  }

  // Default fallback: JSON input + output
  return (
    <div className="space-y-1.5">
      <pre className="overflow-x-auto rounded-md bg-muted px-3 py-2 text-xs font-mono text-foreground max-h-40">
        {JSON.stringify(input, null, 2)}
      </pre>
      {result && (
        <pre
          className={cn(
            "overflow-x-auto rounded-md px-3 py-2 text-xs font-mono max-h-40",
            result.isError
              ? "bg-destructive/10 text-destructive"
              : "bg-muted text-foreground",
          )}
        >
          {result.output}
        </pre>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ToolCallBubble
// ---------------------------------------------------------------------------

export function ToolCallBubble({ call, result }: Props) {
  const [open, setOpen] = useState(false);
  const { Icon, label, color } = toolMeta(call.tool);
  const summary = summariseInput(call.tool, call.input);
  const pending = !result;

  return (
    <div className="rounded-lg border bg-card text-sm">
      {/* Header row — always visible */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-accent/40 rounded-lg"
        aria-expanded={open}
      >
        <Icon className={cn("size-3.5 shrink-0", color)} />
        <span className="font-medium text-foreground">{label}</span>
        <span className="flex-1 truncate font-mono text-xs text-muted-foreground">
          {summary}
        </span>
        {pending ? (
          <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
        ) : result?.isError ? (
          <AlertCircle className="size-3.5 shrink-0 text-destructive" />
        ) : open ? (
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
        )}
      </button>

      {/* Expandable body */}
      {open && !pending && (
        <div className="border-t px-3 pb-3 pt-2">
          <ToolBody call={call} result={result} />
        </div>
      )}
    </div>
  );
}
