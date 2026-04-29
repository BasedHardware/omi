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

/** Metadata about the Pi session that is currently loaded in the sidecar. */
export interface CurrentSession {
  /** Absolute path to the JSONL session file on disk. */
  file?: string;
  /** Pi's internal session UUID. */
  id?: string;
  /** Human-readable session name (set by Pi or renamed by user). */
  name?: string;
}

export interface UseCodingAgent {
  pickFolder: () => Promise<string | null>;
  startSession: (folder: string, prompt: string, model?: string, sessionPath?: string) => Promise<string>;
  sendMessage: (sessionId: string, message: string) => Promise<void>;
  sendRawRpc: (sessionId: string, jsonValue: unknown) => Promise<void>;
  stopSession: (sessionId: string) => Promise<void>;
  pushUserText: (text: string) => void;
  pushError: (message: string) => void;
  events: AgentEvent[];
  isStreaming: boolean;
  /** Metadata about the Pi session resolved after `startSession`. */
  currentSession: CurrentSession | null;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BACKEND_URL = "https://nooto-dev.togodynamics.com";

// Pi event types that carry no displayable content — silently dropped.
const SILENT_PI_TYPES = new Set([
  "agent_start",
  "turn_start",
  "turn_end",
  "tool_execution_start",
  "tool_execution_update",
  "queue_update",
  "compaction_start",
  "compaction_end",
  "auto_retry_start",
  "auto_retry_end",
]);

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

  if (piType && SILENT_PI_TYPES.has(piType)) return null;

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

// Convert a Pi `Message` JSON object (from a JSONL session entry's
// `message` field) into the AgentEvent[] our UI renders. Used to replay
// history when a session is restored — Pi's switch_session loads state
// silently, so we have to reconstruct the chat ourselves.
function piMessageToEvents(msg: unknown): AgentEvent[] {
  if (typeof msg !== "object" || msg === null) return [];
  const m = msg as Record<string, unknown>;
  const role = m.role as string | undefined;
  const contentArr = (m.content as Array<Record<string, unknown>> | undefined) ?? [];

  if (role === "user") {
    const text = contentArr
      .filter((c) => c.type === "text" && typeof c.text === "string")
      .map((c) => String(c.text))
      .join("");
    return text ? [{ type: "user_text", text }] : [];
  }

  if (role === "assistant") {
    const out: AgentEvent[] = [];
    for (const c of contentArr) {
      if (c.type === "text" && typeof c.text === "string" && c.text.length > 0) {
        out.push({ type: "text", text: String(c.text) });
      } else if (c.type === "toolCall") {
        out.push({
          type: "tool_call",
          tool: String(c.name ?? ""),
          input: c.arguments,
          id: String(c.id ?? ""),
        });
      }
    }
    return out;
  }

  if (role === "toolResult") {
    const text = contentArr
      .filter((c) => c.type === "text" && typeof c.text === "string")
      .map((c) => String(c.text))
      .join("");
    return [
      {
        type: "tool_result",
        id: String(m.toolCallId ?? ""),
        output: text,
        isError: Boolean(m.isError),
      },
    ];
  }

  return [];
}

// Extract session metadata from a Pi `get_state` response event.
// Pi responds with `{ type: "response", command: "get_state", state: { sessionFile, sessionId, sessionName, … } }`.
function extractGetStateSession(line: unknown): CurrentSession | null {
  if (typeof line !== "object" || line === null) return null;
  const event = line as Record<string, unknown>;
  if (event.type !== "response" || event.command !== "get_state") return null;
  const state = event.state as Record<string, unknown> | undefined;
  if (!state) return null;
  return {
    file: typeof state.sessionFile === "string" ? state.sessionFile : undefined,
    id: typeof state.sessionId === "string" ? state.sessionId : undefined,
    name: typeof state.sessionName === "string" ? state.sessionName : undefined,
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useCodingAgent(): UseCodingAgent {
  const idToken = useAuthStore((s) => s.idToken);
  const refreshToken = useAuthStore((s) => s.refreshToken);

  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentSession, setCurrentSession] = useState<CurrentSession | null>(null);

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

        const sessionMeta = extractGetStateSession(line);
        if (sessionMeta !== null) {
          setCurrentSession(sessionMeta);
          return; // `get_state` response is internal; don't surface to events[]
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
    async (folder: string, prompt: string, model?: string, sessionPath?: string): Promise<string> => {
      let token = idToken;
      if (!token) {
        const ok = await refreshToken();
        if (!ok) throw new Error("Not signed in — cannot start coding agent session");
        token = useAuthStore.getState().idToken;
      }
      if (!token) throw new Error("ID token unavailable");

      const sessionId = crypto.randomUUID();
      activeSessionRef.current = sessionId;
      setCurrentSession(null);
      setIsStreaming(true);

      // Replay prior history when restoring an existing session, otherwise
      // start with an empty chat.
      if (sessionPath) {
        try {
          const messages = await invoke<unknown[]>("coding_agent_load_session_messages", {
            filePath: sessionPath,
          });
          const replayed = messages.flatMap(piMessageToEvents);
          setEvents(replayed);
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn("[coding-agent] failed to load session history:", err);
          setEvents([]);
        }
      } else {
        setEvents([]);
      }

      await invoke("coding_agent_start_session", {
        folder,
        prompt,
        sessionId,
        idToken: token,
        backendUrl: BACKEND_URL,
        model,
        sessionPath: sessionPath ?? null,
      });

      // Ask Pi to report the resolved session metadata (file path, id, name).
      // The response arrives as a `coding-agent:event` with type="response",
      // command="get_state" and is captured by the listener above.
      await invoke("coding_agent_send_raw_rpc", {
        sessionId,
        jsonValue: { type: "get_state" },
      }).catch(() => {
        // Non-fatal: session metadata just won't be populated.
      });

      return sessionId;
    },
    [idToken, refreshToken],
  );

  const sendMessage = useCallback(async (sessionId: string, message: string): Promise<void> => {
    setIsStreaming(true);
    await invoke("coding_agent_send_message", { sessionId, message });
  }, []);

  const sendRawRpc = useCallback(async (sessionId: string, jsonValue: unknown): Promise<void> => {
    await invoke("coding_agent_send_raw_rpc", { sessionId, jsonValue });
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
    sendRawRpc,
    stopSession,
    pushUserText,
    pushError,
    events,
    isStreaming,
    currentSession,
  };
}
