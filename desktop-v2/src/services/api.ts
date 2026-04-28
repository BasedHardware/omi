/**
 * API client for the Nooto desktop app.
 *
 * Chat calls Gemini directly (no backend proxy needed).
 * The API key is fetched from the Tauri backend via IPC.
 * Message history is persisted locally via Zustand persist.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { nanoid } from "nanoid";
import type Anthropic from "@anthropic-ai/sdk";

import { CHAT_TOOLS, executeToolCall } from "@/services/chat";

const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta";

// ---------------------------------------------------------------------------
// Gemini tool schema conversion
// ---------------------------------------------------------------------------

interface GeminiSchema {
  type: string;
  properties?: Record<string, GeminiSchema>;
  required?: string[];
  description?: string;
  enum?: string[];
}

interface GeminiFunctionDeclaration {
  name: string;
  description?: string;
  parameters?: GeminiSchema;
}

/** Anthropic input_schema → Gemini parameters. The two formats are compatible
 *  for our simple shapes; we just strip `additionalProperties` (Gemini errors
 *  on it) and recurse. */
function anthropicSchemaToGemini(schema: Anthropic.Tool["input_schema"]): GeminiSchema {
  const out: GeminiSchema = { type: schema.type ?? "object" };
  if (schema.properties) {
    out.properties = {};
    for (const [k, v] of Object.entries(schema.properties as Record<string, GeminiSchema>)) {
      out.properties[k] = {
        type: v.type ?? "string",
        ...(v.description ? { description: v.description } : {}),
        ...(v.enum ? { enum: v.enum } : {}),
      };
    }
  }
  if ((schema as { required?: string[] }).required) {
    out.required = (schema as { required?: string[] }).required;
  }
  return out;
}

let geminiFunctionDeclarationsCache: GeminiFunctionDeclaration[] | null = null;

function geminiFunctionDeclarations(): GeminiFunctionDeclaration[] {
  if (!geminiFunctionDeclarationsCache) {
    geminiFunctionDeclarationsCache = CHAT_TOOLS.map((t) => ({
      name: t.name,
      description: t.description,
      parameters: anthropicSchemaToGemini(t.input_schema),
    }));
  }
  return geminiFunctionDeclarationsCache;
}

// ---------------------------------------------------------------------------
// Gemini wire types (subset we use)
// ---------------------------------------------------------------------------

type GeminiPart =
  | { text: string }
  | { functionCall: { name: string; args?: Record<string, unknown> } }
  | { functionResponse: { name: string; response: { content: string } } };

interface GeminiContent {
  role: "user" | "model";
  parts: GeminiPart[];
}

// ---------------------------------------------------------------------------
// API key management
// ---------------------------------------------------------------------------

let cachedApiKey: string | null = null;

export async function getGeminiApiKey(): Promise<string> {
  if (cachedApiKey) return cachedApiKey;

  const key = await invoke<string | null>("get_gemini_api_key");
  if (!key) {
    throw new Error(
      "GEMINI_API_KEY not configured. Add it to desktop-v2/src-tauri/.env",
    );
  }
  cachedApiKey = key;
  return key;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ServerMessage {
  id: string;
  created_at: string;
  text: string;
  sender: "ai" | "human";
  type: string;
  plugin_id?: string | null;
  from_integration?: boolean;
  memories?: { id: string; structured: { title: string; emoji: string } }[];
  ask_for_nps?: boolean;
}

// ---------------------------------------------------------------------------
// Chat via Gemini streaming (direct, no backend proxy)
// ---------------------------------------------------------------------------

interface GeminiCallbacks {
  onDelta: (text: string) => void;
  onToolCall?: (id: string, name: string, input: unknown) => void;
  onToolResult?: (id: string, name: string, output: string) => void;
}

const MAX_GEMINI_TOOL_ITERATIONS = 6;

/** One non-streaming Gemini turn. Returns the candidate's parts so the caller
 *  can either emit text or dispatch tool calls. We use non-streaming because
 *  Gemini's streaming endpoint mixes function-call parts and text deltas in a
 *  way that's tedious to incrementally render — short-circuit by collecting
 *  the full message, then synthesizing onDelta with the text part(s). */
async function geminiGenerate(
  apiKey: string,
  systemPrompt: string,
  contents: GeminiContent[],
): Promise<GeminiPart[]> {
  const url = `${GEMINI_BASE}/models/gemini-2.5-flash:generateContent?key=${apiKey}`;
  const body = {
    system_instruction: { parts: [{ text: systemPrompt }] },
    contents,
    tools: [{ functionDeclarations: geminiFunctionDeclarations() }],
    generationConfig: { maxOutputTokens: 4096 },
  };

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "");
    throw new Error(`Chat error: ${response.status} ${errorText}`);
  }

  const data = (await response.json()) as {
    candidates?: { content?: { parts?: GeminiPart[] } }[];
  };
  return data.candidates?.[0]?.content?.parts ?? [];
}

async function sendChatViaGemini(
  text: string,
  onDelta: ((text: string) => void) | GeminiCallbacks,
  conversationHistory?: { role: "user" | "assistant"; content: string }[],
  systemPrompt?: string,
): Promise<string> {
  const apiKey = await getGeminiApiKey();
  const callbacks: GeminiCallbacks =
    typeof onDelta === "function" ? { onDelta } : onDelta;

  const effectiveSystemPrompt =
    systemPrompt ??
    `You are Nooto, an AI assistant integrated into the user's desktop app. You help with questions about their day, notes, screen activity, and tasks. Be concise and helpful.`;

  const contents: GeminiContent[] = [];

  if (conversationHistory) {
    for (const msg of conversationHistory) {
      contents.push({
        role: msg.role === "user" ? "user" : "model",
        parts: [{ text: msg.content }],
      });
    }
  }

  contents.push({ role: "user", parts: [{ text }] });

  let fullText = "";

  for (let iter = 0; iter < MAX_GEMINI_TOOL_ITERATIONS; iter++) {
    const parts = await geminiGenerate(apiKey, effectiveSystemPrompt, contents);

    const functionCalls = parts.filter(
      (p): p is { functionCall: { name: string; args?: Record<string, unknown> } } =>
        "functionCall" in p,
    );
    const textParts = parts.filter((p): p is { text: string } => "text" in p);

    // Emit any text the model produced this turn.
    for (const tp of textParts) {
      if (tp.text) {
        fullText += tp.text;
        callbacks.onDelta(tp.text);
      }
    }

    if (functionCalls.length === 0) {
      break;
    }

    // Append the model's full turn (text + function calls) to history.
    contents.push({ role: "model", parts });

    // Execute each function call and append its response.
    const responseParts: GeminiPart[] = [];
    for (let i = 0; i < functionCalls.length; i++) {
      const fc = functionCalls[i].functionCall;
      // Gemini doesn't return ids for function calls — synthesize one so the
      // UI can address the resulting card.
      const callId = `gemini-tool-${iter}-${i}-${Date.now()}`;
      callbacks.onToolCall?.(callId, fc.name, fc.args ?? {});
      const output = await executeToolCall(fc.name, fc.args ?? {});
      callbacks.onToolResult?.(callId, fc.name, output);

      responseParts.push({
        functionResponse: {
          name: fc.name,
          response: { content: output },
        },
      });
    }
    contents.push({ role: "user", parts: responseParts });
  }

  return fullText;
}

// ---------------------------------------------------------------------------
// Backend chat (SSE) — routes through the Nooto backend so plugin chat tools
// (Jira, Linear, ClickUp, …) are available. The backend agent loads enabled
// plugins' chat_tools and dispatches calls to their `/tools/*` endpoints
// automatically; we just need to consume the SSE stream and surface text +
// tool-call cards. Wire format mirrors `app/lib/backend/http/api/messages.dart`.
// ---------------------------------------------------------------------------

import { useAuthStore as _useAuthStoreForChat } from "@/stores/authStore";

interface BackendChatCallbacks {
  onDelta: (text: string) => void;
  /** Fired for each `think:` line. `appId` is null when the agent is "thinking"
   *  outside any plugin (loading context, deciding tools). */
  onThink?: (text: string, appId: string | null) => void;
  /** Fired when the backend agent dispatches a plugin tool whose response
   *  contained structured `data` (e.g. Jira's `data.tasks[]`). The frontend
   *  uses this to render rich cards inline in the chat instead of falling
   *  back to the markdown summary the LLM consumes. */
  onToolResult?: (payload: ToolResultFrame) => void;
  /** Final ResponseMessage from `done:` — text already streamed via onDelta,
   *  but this carries citations/memories/ask_for_nps. */
  onDone?: (response: ServerMessage) => void;
}

export interface ToolResultFrame {
  app_id: string | null;
  tool_name: string;
  data: Record<string, unknown>;
}

interface BackendChatStreamResult {
  status: number;
  error_body: string | null;
}

function decodeBase64Utf8(b64: string): string {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder("utf-8").decode(bytes);
}

function parseChatLine(line: string, callbacks: BackendChatCallbacks): void {
  // `data:` and `think:` chunks have `\n` escaped to `__CRLF__` — undo that
  // before forwarding so multi-line responses render correctly.
  if (line.startsWith("data: ")) {
    callbacks.onDelta(line.slice(6).replaceAll("__CRLF__", "\n"));
    return;
  }
  if (line.startsWith("think: ")) {
    const raw = line.slice(7).replaceAll("__CRLF__", "\n");
    // Format: `<text>|app_id:<id>` (omit the suffix when no app is involved).
    const sep = raw.lastIndexOf("|app_id:");
    if (sep >= 0) {
      callbacks.onThink?.(raw.slice(0, sep), raw.slice(sep + "|app_id:".length));
    } else {
      callbacks.onThink?.(raw, null);
    }
    return;
  }
  if (line.startsWith("done: ")) {
    try {
      const parsed = JSON.parse(decodeBase64Utf8(line.slice(6))) as ServerMessage;
      callbacks.onDone?.(parsed);
    } catch (e) {
      console.warn("[chat] failed to decode done frame", e);
    }
    return;
  }
  if (line.startsWith("tool_result: ")) {
    try {
      const parsed = JSON.parse(decodeBase64Utf8(line.slice(13))) as ToolResultFrame;
      callbacks.onToolResult?.(parsed);
    } catch (e) {
      console.warn("[chat] failed to decode tool_result frame", e);
    }
    return;
  }
  if (line.startsWith("message: ")) {
    // Voice flow only; ignore for text chat.
    return;
  }
}

async function sendChatViaBackendOnce(
  text: string,
  callbacks: BackendChatCallbacks,
  appId: string | null,
  token: string | null,
): Promise<BackendChatStreamResult> {
  const requestId = nanoid();
  const url =
    appId && appId !== "null" && appId !== "no_selected"
      ? `${BACKEND_URL}/v2/messages?app_id=${encodeURIComponent(appId)}`
      : `${BACKEND_URL}/v2/messages`;

  const unlistenLine = await listen<{ request_id: string; line: string }>(
    "chat:stream",
    (event) => {
      if (event.payload.request_id !== requestId) return;
      parseChatLine(event.payload.line, callbacks);
    },
  );
  let unlistenDone: (() => void) | null = null;
  const doneSignal = new Promise<void>((resolve) => {
    void listen<{ request_id: string }>("chat:stream:done", (event) => {
      if (event.payload.request_id !== requestId) return;
      resolve();
    }).then((fn) => {
      unlistenDone = fn as (() => void) | null;
    });
  });

  try {
    const result = await invoke<BackendChatStreamResult>("backend_chat_stream", {
      args: {
        url,
        token,
        body: JSON.stringify({ text }),
        request_id: requestId,
      },
    });
    if (result.status >= 200 && result.status < 300) {
      // Wait briefly for any final `chat:stream:done` event still in flight.
      await Promise.race([
        doneSignal,
        new Promise((r) => setTimeout(r, 100)),
      ]);
    }
    return result;
  } finally {
    unlistenLine();
    if (unlistenDone) (unlistenDone as () => void)();
  }
}

export async function sendChatViaBackend(
  text: string,
  callbacks: BackendChatCallbacks,
  options: { appId?: string | null } = {},
): Promise<void> {
  const authStore = _useAuthStoreForChat.getState();
  let token = authStore.idToken;
  if (!token) {
    throw new Error("Sign in to chat with the Nooto agent (plugin tools require auth).");
  }

  let result = await sendChatViaBackendOnce(text, callbacks, options.appId ?? null, token);

  if (result.status === 401) {
    try {
      const refreshed = await _useAuthStoreForChat.getState().refreshToken();
      if (refreshed) {
        token = _useAuthStoreForChat.getState().idToken;
        result = await sendChatViaBackendOnce(text, callbacks, options.appId ?? null, token);
      }
    } catch (err) {
      console.warn("[chat] token refresh failed:", err);
    }
  }

  if (result.status < 200 || result.status >= 300) {
    throw new ApiError(
      result.status,
      result.error_body ?? "",
      `Chat error: ${result.status}`,
    );
  }
}

// ---------------------------------------------------------------------------
// Backend REST helpers — routes CRUD to the remote OMI/Nooto API
// ---------------------------------------------------------------------------

import { useAuthStore } from "@/stores/authStore";

/**
 * The Nooto backend (dev). Tasks, memories, and conversations are all stored
 * in Firestore behind this API. We authenticate using the Firebase ID token
 * obtained during sign-in. Same host used by the Swift dev desktop app
 * (`desktop/run-local.sh`).
 */
const BACKEND_URL = "https://nooto-dev.togodynamics.com";

interface RustBackendResponse {
  status: number;
  body: string;
}

async function backendRequest<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const { method = "GET", body } = options;

  const doFetch = async (token: string | null): Promise<RustBackendResponse> =>
    invoke<RustBackendResponse>("backend_request", {
      args: {
        method,
        url: `${BACKEND_URL}${path}`,
        token,
        body: body != null ? JSON.stringify(body) : null,
      },
    });

  let token = useAuthStore.getState().idToken;
  let response = await doFetch(token);

  if (response.status === 401 && token) {
    try {
      const refreshed = await useAuthStore.getState().refreshToken();
      if (refreshed) {
        token = useAuthStore.getState().idToken;
        response = await doFetch(token);
      }
    } catch (err) {
      console.warn("[api] token refresh failed:", err);
    }
  }

  if (response.status < 200 || response.status >= 300) {
    console.error(`[api] ${method} ${path} → ${response.status}`, response.body.slice(0, 300));
    throw new ApiError(response.status, response.body, `API error: ${response.status}`);
  }

  return response.body ? (JSON.parse(response.body) as T) : (undefined as T);
}

/** Thrown by `backendRequest` on non-2xx so callers can react to specific
 *  status codes / detail strings (e.g. 400 "App setup is not completed"
 *  needs to launch the plugin's OAuth start URL). */
export class ApiError extends Error {
  status: number;
  body: string;
  constructor(status: number, body: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
  /** Best-effort access to FastAPI's `{"detail": "..."}` payload. */
  get detail(): string | null {
    try {
      const parsed = JSON.parse(this.body);
      return typeof parsed?.detail === "string" ? parsed.detail : null;
    } catch {
      return null;
    }
  }
}

// ---------------------------------------------------------------------------
// Integration writeback — dispatches a "mark this ticket done" call to the
// plugin's update tool. Used by the Plan view's two-way sync toggle (Slice D).
// Each plugin uses its own tool name; we look it up in the app's chat_tools
// manifest so this stays generic across Jira/Linear/etc.
// ---------------------------------------------------------------------------

interface IntegrationToggleResult {
  ok: boolean;
  /** Human-readable error from the plugin (e.g. "Issue/project not found"). */
  error?: string;
}

interface ChatToolWireResponse {
  result?: string;
  error?: string | null;
  oauth_url?: string | null;
  data?: unknown;
}

/** Dispatch a "complete" writeback to a plugin's `update_*_status` tool.
 *
 *  Caller passes the plugin's `app_home_url` (origin) and the tool name lifted
 *  from the app's `chat_tools` manifest. We POST to `{home}/tools/{name}` with
 *  `{uid, issue_key, new_status}` — the shape `nooto-jira-app`'s
 *  `update_issue_status` route already accepts. The Linear plugin doesn't
 *  expose an equivalent tool today, so callers should fall back gracefully. */
export async function dispatchIntegrationToggle(args: {
  appHomeUrl: string;
  toolName: string;
  uid: string;
  externalId: string;
  newStatus: string;
}): Promise<IntegrationToggleResult> {
  const { appHomeUrl, toolName, uid, externalId, newStatus } = args;
  const url = `${appHomeUrl.replace(/\/$/, "")}/tools/${toolName}`;
  try {
    const response = await invoke<RustBackendResponse>("backend_request", {
      args: {
        method: "POST",
        url,
        token: null, // plugin tools authenticate via the `uid` body, not a bearer
        body: JSON.stringify({
          uid,
          issue_key: externalId,
          new_status: newStatus,
        }),
      },
    });
    if (response.status < 200 || response.status >= 300) {
      return { ok: false, error: `${response.status}: ${response.body.slice(0, 200)}` };
    }
    const parsed = response.body
      ? (JSON.parse(response.body) as ChatToolWireResponse)
      : {};
    if (parsed.error) return { ok: false, error: parsed.error };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

interface BackendPingResult {
  status: number | null;
  body_preview: string;
  elapsed_ms: number;
  error: string | null;
}

export async function debugBackendPing(path = "/v1/action-items"): Promise<BackendPingResult> {
  const token = useAuthStore.getState().idToken;
  const url = `${BACKEND_URL}${path}`;
  console.info(`[debug] pinging ${url} via Rust reqwest…`);
  const result = await invoke<BackendPingResult>("debug_backend_ping", { url, token });
  console.info(`[debug] result:`, result);
  return result;
}

if (typeof window !== "undefined") {
  (window as unknown as { debugBackendPing: typeof debugBackendPing }).debugBackendPing =
    debugBackendPing;
}

export const api = {
  get: <T>(path: string) => backendRequest<T>(path),
  post: <T>(path: string, body: unknown) => backendRequest<T>(path, { method: "POST", body }),
  put: <T>(path: string, body: unknown) => backendRequest<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body: unknown) => backendRequest<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => backendRequest<T>(path, { method: "DELETE" }),
  sendChatViaGemini,
  debugPing: debugBackendPing,
};
