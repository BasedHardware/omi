/**
 * TerminalPane — collapsible panel that shows live output from `dispatch_bash`
 * tool calls.
 *
 * ## Data flow
 *
 * The `dispatch_bash` Pi extension feeds output chunks via the `onUpdate`
 * callback inside its `execute` function. Pi serialises each `onUpdate` call
 * as a `tool_execution_update` RPC event, which Tauri's existing stdout reader
 * in `coding_agent.rs` forwards as a `coding-agent:event` Tauri event.
 *
 * This component subscribes to `coding-agent:event` once per session and
 * dispatches on `type` to handle both streaming updates and final results.
 *
 * ## v1 limitations
 *
 * - ANSI escape codes render as raw text. Add `ansi-to-html` or xterm.js later.
 * - Terminals from previous sessions are not restored on remount.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { Terminal, X, ChevronDown, ChevronUp, Loader2, CircleCheck } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TerminalEntry {
  terminal_id: string;
  description: string;
  output: string;
  running: boolean;
  exit_code?: number;
}

interface DispatchBashPayload {
  terminal_id: string;
  description: string;
  output_so_far?: string;
  output?: string;
  still_running: boolean;
  exit_code?: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Extract the first text content block from a Pi tool result/update payload. */
function extractTextPayload(container: Record<string, unknown> | null | undefined): DispatchBashPayload | null {
  if (!container) return null;
  const contentArr = container.content as Array<{ type: string; text: string }> | undefined;
  const text = contentArr?.find((c) => c.type === "text")?.text;
  if (!text) return null;
  try {
    return JSON.parse(text) as DispatchBashPayload;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// TerminalPane
// ---------------------------------------------------------------------------

interface TerminalPaneProps {
  sessionId: string | null;
}

export function TerminalPane({ sessionId }: TerminalPaneProps) {
  const [terminals, setTerminals] = useState<TerminalEntry[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const outputRef = useRef<HTMLPreElement>(null);

  // -----------------------------------------------------------------------
  // Single listener for all dispatch_bash events
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!sessionId) return;

    let unlisten: UnlistenFn | null = null;
    let cancelled = false;

    const listenPromise = listen<{ session_id: string; line: unknown }>(
      "coding-agent:event",
      (e) => {
        const { session_id, line } = e.payload;
        if (session_id !== sessionId) return;

        const event = line as Record<string, unknown> | null;
        if (!event || typeof event !== "object") return;
        if (event.toolName !== "dispatch_bash") return;

        if (event.type === "tool_execution_update") {
          const partial = extractTextPayload(event.partialResult as Record<string, unknown> | null);
          if (!partial?.terminal_id) return;

          const { terminal_id, description, output_so_far = "", still_running } = partial;

          setTerminals((prev) => {
            const idx = prev.findIndex((t) => t.terminal_id === terminal_id);
            if (idx === -1) {
              setActiveId(terminal_id);
              return [...prev, { terminal_id, description, output: output_so_far, running: still_running }];
            }
            const updated = [...prev];
            updated[idx] = { ...updated[idx], output: output_so_far, running: still_running };
            return updated;
          });
        } else if (event.type === "tool_execution_end") {
          const final = extractTextPayload(event.result as Record<string, unknown> | null);
          if (!final?.terminal_id) return;

          const { terminal_id, output, exit_code } = final;

          setTerminals((prev) => {
            const idx = prev.findIndex((t) => t.terminal_id === terminal_id);
            if (idx === -1) return prev;
            const updated = [...prev];
            updated[idx] = {
              ...updated[idx],
              running: false,
              exit_code: exit_code ?? 0,
              output: output ?? updated[idx].output,
            };
            return updated;
          });
        }
      },
    );

    listenPromise.then((fn) => {
      if (cancelled) fn();
      else unlisten = fn;
    });

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [sessionId]);

  // Reset when session changes.
  useEffect(() => {
    setTerminals([]);
    setActiveId(null);
  }, [sessionId]);

  // Auto-scroll only the active terminal's output pane.
  useEffect(() => {
    if (outputRef.current && !collapsed) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [activeId, collapsed, terminals]);

  // -----------------------------------------------------------------------
  // Dismiss a terminal tab
  // -----------------------------------------------------------------------
  const dismiss = useCallback((id: string) => {
    setTerminals((prev) => {
      const next = prev.filter((t) => t.terminal_id !== id);
      setActiveId((cur) => (cur === id ? (next[next.length - 1]?.terminal_id ?? null) : cur));
      return next;
    });
  }, []);

  if (terminals.length === 0) return null;

  const activeTerminal =
    terminals.find((t) => t.terminal_id === activeId) ?? terminals[terminals.length - 1];

  return (
    <div className="mx-5 mb-3 overflow-hidden rounded-lg border border-border bg-zinc-950">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
        <Terminal className="size-3.5 shrink-0 text-zinc-400" />

        {/* Tabs */}
        <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {terminals.map((t) => (
            <button
              key={t.terminal_id}
              type="button"
              onClick={() => setActiveId(t.terminal_id)}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded px-2 py-0.5 text-xs transition-colors",
                t.terminal_id === activeTerminal.terminal_id
                  ? "bg-white/10 text-zinc-100"
                  : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300",
              )}
            >
              {t.running ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <CircleCheck
                  className={cn("size-3", t.exit_code === 0 ? "text-emerald-400" : "text-red-400")}
                />
              )}
              <span className="max-w-[160px] truncate">{t.description}</span>
              <button
                type="button"
                onClick={(ev) => {
                  ev.stopPropagation();
                  dismiss(t.terminal_id);
                }}
                className="ml-0.5 rounded p-0.5 hover:bg-white/10"
                aria-label={`Close ${t.description}`}
              >
                <X className="size-2.5" />
              </button>
            </button>
          ))}
        </div>

        {/* Collapse / expand */}
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="ml-auto shrink-0 rounded p-0.5 text-zinc-500 hover:bg-white/10 hover:text-zinc-300"
          aria-label={collapsed ? "Expand terminal" : "Collapse terminal"}
        >
          {collapsed ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
        </button>
      </div>

      {/* Output body */}
      {!collapsed && (
        <pre
          ref={outputRef}
          className="max-h-64 overflow-y-auto px-3 py-2 font-mono text-xs leading-5 text-zinc-200"
          style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}
        >
          {activeTerminal.output || (
            <span className="text-zinc-500 italic">Waiting for output…</span>
          )}
        </pre>
      )}
    </div>
  );
}
