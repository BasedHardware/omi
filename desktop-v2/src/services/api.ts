/**
 * API client for the Nooto desktop app.
 *
 * Chat calls Gemini directly (no backend proxy needed).
 * The API key is fetched from the Tauri backend via IPC.
 * Message history is persisted locally via Zustand persist.
 */

import { invoke } from "@tauri-apps/api/core";
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

async function getGeminiApiKey(): Promise<string> {
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

  const doFetch = async (token: string | null): Promise<RustBackendResponse> => {
    console.info(`[api] ${method} ${path} (token=${token ? "yes" : "NO"})`);
    const resp = await invoke<RustBackendResponse>("backend_request", {
      args: {
        method,
        url: `${BACKEND_URL}${path}`,
        token,
        body: body != null ? JSON.stringify(body) : null,
      },
    });
    console.info(`[api] ${method} ${path} → ${resp.status}`);
    return resp;
  };

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
    throw new Error(`API error: ${response.status}`);
  }

  return response.body ? (JSON.parse(response.body) as T) : (undefined as T);
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
