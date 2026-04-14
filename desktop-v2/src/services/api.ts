/**
 * API client for the Nooto desktop app.
 *
 * Chat calls Gemini directly (no backend proxy needed).
 * The API key is fetched from the Tauri backend via IPC.
 * Message history is persisted locally via Zustand persist.
 */

import { invoke } from "@tauri-apps/api/core";

const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta";

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

async function sendChatViaGemini(
  text: string,
  onDelta: (text: string) => void,
  conversationHistory?: { role: "user" | "assistant"; content: string }[],
): Promise<string> {
  const apiKey = await getGeminiApiKey();
  const url = `${GEMINI_BASE}/models/gemini-2.5-flash:streamGenerateContent?alt=sse&key=${apiKey}`;

  const systemPrompt = `You are Nooto, an AI assistant integrated into the user's desktop app. You help with questions about their day, notes, screen activity, and tasks. Be concise and helpful.`;

  const contents: { role: string; parts: { text: string }[] }[] = [];

  if (conversationHistory) {
    for (const msg of conversationHistory) {
      contents.push({
        role: msg.role === "user" ? "user" : "model",
        parts: [{ text: msg.content }],
      });
    }
  }

  contents.push({
    role: "user",
    parts: [{ text }],
  });

  const body = {
    system_instruction: { parts: [{ text: systemPrompt }] },
    contents,
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

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let fullText = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const jsonStr = line.slice(6).trim();
      if (!jsonStr || jsonStr === "[DONE]") continue;

      try {
        const parsed = JSON.parse(jsonStr);
        const delta = parsed?.candidates?.[0]?.content?.parts?.[0]?.text;
        if (delta) {
          fullText += delta;
          onDelta(delta);
        }
      } catch {
        // skip malformed JSON
      }
    }
  }

  if (buffer.trim() && buffer.startsWith("data: ")) {
    const jsonStr = buffer.slice(6).trim();
    if (jsonStr && jsonStr !== "[DONE]") {
      try {
        const parsed = JSON.parse(jsonStr);
        const delta = parsed?.candidates?.[0]?.content?.parts?.[0]?.text;
        if (delta) {
          fullText += delta;
          onDelta(delta);
        }
      } catch {
        // skip
      }
    }
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
