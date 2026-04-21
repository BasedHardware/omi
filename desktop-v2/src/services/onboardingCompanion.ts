/**
 * Streaming Gemini client used by the onboarding Companion panel.
 *
 * Lives separately from `services/api.ts` because the onboarding flow needs
 * server-streamed tokens (so the right-pane chat feels alive as the user
 * reads) and doesn't want the tool-calling plumbing baked into the main
 * chat helper. This is a deliberately small, single-purpose helper — one
 * Gemini endpoint, one streaming parser, zero tools.
 */
import { invoke } from "@tauri-apps/api/core";

const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta";
const MODEL = "gemini-2.5-flash";

/** Flat role/content pair sent to Gemini as a conversation turn. The rich
 *  chat-flow `CompanionTurn` (see chatFlow/types.ts) lives in the store and
 *  is flattened down to this shape when building the request. */
export interface GeminiHistoryTurn {
  role: "user" | "assistant";
  content: string;
}

/** @deprecated — preserved for any external references while we transition. */
export type CompanionTurn = GeminiHistoryTurn;

interface GeminiPart {
  text?: string;
}

interface GeminiContent {
  role: "user" | "model";
  parts: GeminiPart[];
}

interface StreamOptions {
  systemPrompt: string;
  history: GeminiHistoryTurn[];
  /** Forwarded to Gemini as a brand-new user turn. */
  userMessage: string;
  /** Aborts mid-stream. Safe to call even after the response has completed. */
  signal?: AbortSignal;
  /** Called with each appended token chunk. */
  onDelta: (chunk: string) => void;
}

let cachedApiKey: string | null = null;
async function getGeminiApiKey(): Promise<string> {
  if (cachedApiKey) return cachedApiKey;
  const key = await invoke<string | null>("get_gemini_api_key");
  if (!key) {
    throw new Error("GEMINI_API_KEY not configured");
  }
  cachedApiKey = key;
  return key;
}

/**
 * Streams a Gemini response token-by-token into `onDelta`.
 *
 * Resolves with the full text once the stream completes. Rejects if the
 * request fails OR the signal aborts. The parser is tolerant of Gemini's
 * SSE-ish output format (chunks are JSON objects delimited by newlines and
 * `data: ` prefixes — we handle both).
 */
export async function streamCompanionReply(opts: StreamOptions): Promise<string> {
  const apiKey = await getGeminiApiKey();

  const contents: GeminiContent[] = opts.history.map((turn) => ({
    role: turn.role === "user" ? "user" : "model",
    parts: [{ text: turn.content }],
  }));
  contents.push({ role: "user", parts: [{ text: opts.userMessage }] });

  const url = `${GEMINI_BASE}/models/${MODEL}:streamGenerateContent?alt=sse&key=${apiKey}`;
  const body = JSON.stringify({
    system_instruction: { parts: [{ text: opts.systemPrompt }] },
    contents,
    generationConfig: {
      temperature: 0.4,
      maxOutputTokens: 512,
      // Gemini 2.5 "thinking" tokens come out of maxOutputTokens, so a
      // chatty opener can easily be truncated mid-sentence while the model
      // was still reasoning. Cap thinking tightly; the companion doesn't
      // need deep chain-of-thought for 1-2 sentence openers.
      thinkingConfig: {
        thinkingBudget: 0,
      },
    },
  });

  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    signal: opts.signal,
  });

  if (!resp.ok) {
    const errText = await resp.text().catch(() => "");
    throw new Error(`gemini ${resp.status}: ${errText.slice(0, 200)}`);
  }
  if (!resp.body) {
    throw new Error("gemini: empty response body");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let full = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are delimited by \n\n; within a frame each line starts
    // with `data: `. We accept bare JSON lines too for resilience.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      for (const line of frame.split("\n")) {
        const trimmed = line.startsWith("data: ") ? line.slice(6) : line;
        if (!trimmed || trimmed === "[DONE]") continue;
        try {
          const parsed = JSON.parse(trimmed) as {
            candidates?: { content?: { parts?: GeminiPart[] } }[];
          };
          const parts = parsed.candidates?.[0]?.content?.parts ?? [];
          for (const p of parts) {
            if (p.text) {
              full += p.text;
              opts.onDelta(p.text);
            }
          }
        } catch {
          // Ignore malformed frames — streaming responses occasionally
          // split a JSON object across chunks.
        }
      }
    }
  }

  return full;
}
