import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { useAuthStore } from "@/stores/authStore";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type AgentEvent =
  | { type: "user_text"; text: string }
  | { type: "text"; text: string }
  | { type: "tool_call"; tool: string; input: unknown; id: string }
  | { type: "tool_result"; id: string; output: string; isError: boolean }
  | { type: "error"; message: string }
  | { type: "raw"; payload: unknown };

export interface UseCodingAgent {
  pickFolder: () => Promise<string | null>;
  startSession: (folder: string, prompt: string) => Promise<string>;
  sendMessage: (sessionId: string, message: string) => Promise<void>;
  stopSession: (sessionId: string) => Promise<void>;
  pushUserText: (text: string) => void;
  pushError: (message: string) => void;
  events: AgentEvent[];
  isStreaming: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BACKEND_URL = "https://nooto-dev.togodynamics.com";

// ---------------------------------------------------------------------------
// Pi RPC event translation
// ---------------------------------------------------------------------------

// Translate a raw Pi RPC event line into a frontend AgentEvent.
// Returns null for events that carry no displayable content (e.g. internal
// delta types we don't need). Passes unrecognised events through as `raw`
// so the UI can log them without silently dropping information.
function translatePiEvent(line: unknown): AgentEvent | null {
  if (typeof line !== "object" || line === null) return null;

  const event = line as Record<string, unknown>;
  const piType = event.type as string | undefined;

  // Text content delta — the main LLM response stream.
  if (piType === "message_update") {
    const ame = event.assistantMessageEvent as Record<string, unknown> | undefined;
    if (!ame) return null;
    if (ame.type === "text_delta" && typeof ame.delta === "string") {
      return { type: "text", text: ame.delta };
    }
    // toolcall_end carries the fully-assembled tool call object.
    if (ame.type === "toolcall_end") {
      const tc = ame.toolCall as Record<string, unknown> | undefined;
      if (tc) {
        return {
          type: "tool_call",
          tool: String(tc.name ?? ""),
          input: tc.arguments,
          id: String(tc.id ?? ""),
        };
      }
    }
    // All other delta sub-types (text_start, text_end, thinking_*, toolcall_start,
    // toolcall_delta, start, done, error) are not surfaced to the UI.
    return null;
  }

  // Tool execution result.
  if (piType === "tool_execution_end") {
    const result = event.result as Record<string, unknown> | undefined;
    const content = result?.content as Array<Record<string, unknown>> | undefined;
    const text = content?.map((c) => String(c.text ?? "")).join("") ?? "";
    return {
      type: "tool_result",
      id: String(event.toolCallId ?? ""),
      output: text,
      isError: Boolean(event.isError),
    };
  }

  // Extension-level errors.
  if (piType === "extension_error") {
    return { type: "error", message: String(event.error ?? "Extension error") };
  }

  // Auto-retry exhausted.
  if (piType === "auto_retry_end" && event.success === false) {
    return { type: "error", message: String(event.finalError ?? "Agent retry failed") };
  }

  // Agent ended — if it carries an error payload, surface it so silent
  // terminations are visible.
  if (piType === "agent_end") {
    const errMsg = (event.error ?? event.errorMessage) as string | undefined;
    if (typeof errMsg === "string" && errMsg.length > 0) {
      return { type: "error", message: errMsg };
    }
    return null;
  }

  // The AssistantMessage carried by message_start/message_end can include
  // errorMessage + stopReason="error" when the upstream call fails before
  // (or instead of) emitting any text deltas. Surface that error here —
  // otherwise the chat just shows "Thinking…" and ends with no feedback.
  if (piType === "message_start" || piType === "message_end") {
    const msg = event.message as Record<string, unknown> | undefined;
    const errMsg = (msg?.errorMessage ?? msg?.error) as string | undefined;
    const stopReason = msg?.stopReason as string | undefined;
    if (typeof errMsg === "string" && errMsg.length > 0) {
      return { type: "error", message: errMsg };
    }
    if (stopReason === "error" || stopReason === "aborted") {
      return { type: "error", message: `Agent ended with stopReason=${stopReason}` };
    }
    return null;
  }

  // Internal terminal events and other lifecycle events: do not surface as
  // AgentEvents but also do not classify as `raw` — just drop them silently.
  const silentTypes = new Set([
    "agent_start",
    "turn_start",
    "turn_end",
    "tool_execution_start",
    "tool_execution_update",
    "queue_update",
    "compaction_start",
    "compaction_end",
    "auto_retry_start",
    "auto_retry_end", // success=true branch
  ]);
  if (piType && silentTypes.has(piType)) return null;

  // Unrecognised: pass through for debugging.
  return { type: "raw", payload: line };
}

// Return true for Pi events that signal the end of a streaming turn.
function isStreamEndEvent(line: unknown): boolean {
  if (typeof line !== "object" || line === null) return false;
  const t = (line as Record<string, unknown>).type;
  return t === "turn_end" || t === "agent_end";
}

// Return true for Pi events that signal a terminal error.
function isErrorEvent(line: unknown): boolean {
  if (typeof line !== "object" || line === null) return false;
  const event = line as Record<string, unknown>;
  if (event.type === "extension_error") return true;
  if (event.type === "auto_retry_end" && event.success === false) return true;
  return false;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useCodingAgent(): UseCodingAgent {
  const idToken = useAuthStore((s) => s.idToken);
  const refreshToken = useAuthStore((s) => s.refreshToken);

  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  // Track which session is currently active so the event listener can filter.
  const activeSessionRef = useRef<string | null>(null);

  // Wire the Tauri event listener once for the component lifetime.
  // Filtering by session_id means old events from completed sessions are ignored.
  useEffect(() => {
    let unlisten: UnlistenFn | null = null;
    let cancelled = false;

    const listenPromise = listen<{ session_id: string; line: unknown }>(
      "coding-agent:event",
      (e) => {
        const { session_id, line } = e.payload;
        if (session_id !== activeSessionRef.current) return;

        // Always log raw events to the console so silent failures are visible
        // in DevTools without rebuilding.
        // eslint-disable-next-line no-console
        console.log("[coding-agent] raw event:", line);

        if (isStreamEndEvent(line) || isErrorEvent(line)) {
          setIsStreaming(false);
        }

        const translated = translatePiEvent(line);
        if (translated !== null) {
          setEvents((prev) => [...prev, translated]);
        }
      },
    );

    listenPromise.then((fn) => {
      if (cancelled) {
        fn();
      } else {
        unlisten = fn;
      }
    });

    return () => {
      cancelled = true;
      if (unlisten) {
        try {
          unlisten();
        } catch {
          // already unsubscribed
        }
      }
    };
  }, []);

  // ---------------------------------------------------------------------------

  const pickFolder = useCallback(async (): Promise<string | null> => {
    return invoke<string | null>("coding_agent_pick_folder");
  }, []);

  const startSession = useCallback(
    async (folder: string, prompt: string): Promise<string> => {
      let token = idToken;
      if (!token) {
        const ok = await refreshToken();
        if (!ok) throw new Error("Not signed in — cannot start coding agent session");
        token = useAuthStore.getState().idToken;
      }
      if (!token) throw new Error("ID token unavailable");

      const sessionId = crypto.randomUUID();
      activeSessionRef.current = sessionId;
      setEvents([]);
      setIsStreaming(true);

      await invoke("coding_agent_start_session", {
        folder,
        prompt,
        sessionId,
        idToken: token,
        backendUrl: BACKEND_URL,
      });

      return sessionId;
    },
    [idToken, refreshToken],
  );

  const sendMessage = useCallback(async (sessionId: string, message: string): Promise<void> => {
    setIsStreaming(true);
    await invoke("coding_agent_send_message", { sessionId, message });
  }, []);

  const stopSession = useCallback(async (sessionId: string): Promise<void> => {
    setIsStreaming(false);
    if (activeSessionRef.current === sessionId) {
      activeSessionRef.current = null;
    }
    await invoke("coding_agent_stop_session", { sessionId });
  }, []);

  const pushUserText = useCallback((text: string): void => {
    setEvents((prev) => [...prev, { type: "user_text", text }]);
  }, []);

  const pushError = useCallback((message: string): void => {
    setEvents((prev) => [...prev, { type: "error", message }]);
    setIsStreaming(false);
  }, []);

  return {
    pickFolder,
    startSession,
    sendMessage,
    stopSession,
    pushUserText,
    pushError,
    events,
    isStreaming,
  };
}
