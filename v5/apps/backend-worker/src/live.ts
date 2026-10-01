import { withTimeout } from "./wire";

// Live voice session minting. The Worker is the only place project API keys
// live. Clients choose a provider; gpt_live exchanges an SDP offer for an
// OpenAI WebRTC answer, and gemini_live mints a Gemini ephemeral auth token
// for the constrained BidiGenerateContent WebSocket. No key ever reaches JS.
export type LiveVoiceProvider = "gpt_live" | "gemini_live";

export const LIVE_MODEL = "gpt-live-1";
// Responses delegation backend model, matching the OpenAI GPT-Live docs
// example. This is an OpenAI model id, not the OpenRouter chat pin.
export const LIVE_DELEGATION_MODEL = "gpt-5.6-terra";
// Official OpenAI API host only. Do not accept lookalikes, proxies, or http.
export const LIVE_SESSIONS_URL = "https://api.openai.com/v1/live/sessions";
export const LIVE_FETCH_TIMEOUT_MS = 20_000;
export const MAX_SDP_LENGTH = 262_144;

export const GEMINI_LIVE_MODEL = "models/gemini-3.1-flash-live-preview";
export const GEMINI_AUTH_TOKENS_URL =
  "https://generativelanguage.googleapis.com/v1alpha/auth_tokens";
// Constrained BidiGenerateContent WS endpoint. The ephemeral token is passed
// by the client as access_token; the Worker never returns GEMINI_API_KEY.
export const GEMINI_LIVE_WS_URL =
  "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContentConstrained";
const GEMINI_SESSION_START_WINDOW_MIN = 2;
const GEMINI_SESSION_MAX_MIN = 30;
const MAX_GEMINI_TOKEN_LENGTH = 2_048;

const MAX_SESSION_ID_LENGTH = 256;
const MAX_ANSWER_SDP_LENGTH = 1_048_576;
const MAX_INSTRUCTIONS_LENGTH = 4_096;

export const LIVE_INSTRUCTIONS =
  "You are Omi, a concise and helpful personal assistant. Keep spoken replies short. When a request needs current facts, tools, or the user's saved context, delegate it to the backend and speak the result when it is ready.";

export const LIVE_DELEGATION_INSTRUCTIONS =
  "Use the Omi backend to look up the user's saved context. When current facts are needed, use web search. Return concise, grounded results for a spoken conversation.";

export type LiveEnv = {
  OPENAI_API_KEY?: string;
  GEMINI_API_KEY?: string;
};

export const LIVE_REQUEST_MAX_BYTES = 262_144;

export const liveConfigured = (env: LiveEnv): boolean =>
  typeof env.OPENAI_API_KEY === "string" && env.OPENAI_API_KEY.length > 0;

export const geminiLiveConfigured = (env: LiveEnv): boolean =>
  typeof env.GEMINI_API_KEY === "string" && env.GEMINI_API_KEY.length > 0;

export type LiveSessionRequest =
  | { provider: "gpt_live"; sdp: string }
  | { provider: "gemini_live" };

export const parseLiveSessionRequest = (
  value: unknown
): LiveSessionRequest | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const providerRaw = record["provider"];
  // Backward compatible: missing provider with an SDP offer is gpt_live.
  const provider: LiveVoiceProvider | null =
    providerRaw === undefined || providerRaw === null
      ? record["sdp"] !== undefined
        ? "gpt_live"
        : null
      : providerRaw === "gpt_live" || providerRaw === "gemini_live"
      ? providerRaw
      : null;
  if (provider === null) return null;
  if (provider === "gemini_live") {
    return { provider };
  }
  const sdp = record["sdp"];
  if (!isBoundedString(sdp, MAX_SDP_LENGTH)) return null;
  return { provider: "gpt_live", sdp };
};

export type LiveSessionResult =
  | {
      kind: "ok";
      provider: "gpt_live";
      sessionId: string;
      answerSdp: string;
    }
  | {
      kind: "ok";
      provider: "gemini_live";
      sessionId: string;
      token: string;
      model: string;
      url: string;
    }
  | { kind: "error"; status: number; code: string; retryable: boolean };

export const createLiveSession = async (
  env: LiveEnv,
  request: LiveSessionRequest,
  correlationId: string
): Promise<LiveSessionResult> => {
  if (request.provider === "gemini_live") {
    return createGeminiLiveSession(env, correlationId);
  }
  return createGptLiveSession(env, request.sdp, correlationId);
};

async function createGptLiveSession(
  env: LiveEnv,
  sdp: string,
  correlationId: string
): Promise<LiveSessionResult> {
  const apiKey = env.OPENAI_API_KEY ?? "";
  // Fail closed and retryable: a staging deploy without the secret must not
  // look like a client error, and must never invent a key.
  if (apiKey.length === 0) {
    return {
      kind: "error",
      status: 503,
      code: "provider_not_configured",
      retryable: true,
    };
  }
  try {
    return await withTimeout(LIVE_FETCH_TIMEOUT_MS, async (signal) => {
      const response = await fetch(LIVE_SESSIONS_URL, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${apiKey}`,
          "x-omi-correlation-id": correlationId,
        },
        body: JSON.stringify({
          session: {
            model: LIVE_MODEL,
            instructions: truncate(LIVE_INSTRUCTIONS, MAX_INSTRUCTIONS_LENGTH),
            delegation: {
              type: "responses",
              responses: {
                model: LIVE_DELEGATION_MODEL,
                instructions: truncate(
                  LIVE_DELEGATION_INSTRUCTIONS,
                  MAX_INSTRUCTIONS_LENGTH
                ),
                tools: [{ type: "web_search" }],
                tool_choice: "auto",
              },
            },
          },
          transport: { type: "webrtc", sdp },
        }),
        redirect: "manual",
        signal,
      });
      if (!response.ok) {
        logLive("live_session_http_error", correlationId, response.status);
        return {
          kind: "error",
          status: response.status >= 500 ? 503 : 502,
          code: "provider_error",
          retryable: response.status >= 500 || response.status === 429,
        };
      }
      const parsed = parseLiveSessionResponse(await response.json());
      if (parsed === null) {
        logLive("live_session_shape_error", correlationId, response.status);
        return {
          kind: "error",
          status: 502,
          code: "provider_error",
          retryable: true,
        };
      }
      return {
        kind: "ok",
        provider: "gpt_live",
        sessionId: parsed.sessionId,
        answerSdp: parsed.answerSdp,
      };
    });
  } catch {
    logLive("live_session_fetch_error", correlationId, 0);
    return {
      kind: "error",
      status: 503,
      code: "provider_unavailable",
      retryable: true,
    };
  }
}

async function createGeminiLiveSession(
  env: LiveEnv,
  correlationId: string
): Promise<LiveSessionResult> {
  const apiKey = env.GEMINI_API_KEY ?? "";
  if (apiKey.length === 0) {
    return {
      kind: "error",
      status: 503,
      code: "provider_not_configured",
      retryable: true,
    };
  }
  const now = Date.now();
  const start = new Date(
    now + GEMINI_SESSION_START_WINDOW_MIN * 60_000
  ).toISOString();
  const expiresAt = new Date(
    now + GEMINI_SESSION_MAX_MIN * 60_000
  ).toISOString();
  try {
    return await withTimeout(LIVE_FETCH_TIMEOUT_MS, async (signal) => {
      const url = new URL(GEMINI_AUTH_TOKENS_URL);
      url.searchParams.set("key", apiKey);
      const response = await fetch(url.toString(), {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-omi-correlation-id": correlationId,
        },
        body: JSON.stringify({
          uses: 1,
          expireTime: expiresAt,
          newSessionExpireTime: start,
        }),
        redirect: "manual",
        signal,
      });
      if (!response.ok) {
        logLive("gemini_live_http_error", correlationId, response.status);
        return {
          kind: "error",
          status: response.status >= 500 ? 503 : 502,
          code: "provider_error",
          retryable: response.status >= 500 || response.status === 429,
        };
      }
      const body: unknown = await response.json();
      const token = parseGeminiAuthToken(body);
      if (token === null) {
        logLive("gemini_live_shape_error", correlationId, response.status);
        return {
          kind: "error",
          status: 502,
          code: "provider_error",
          retryable: true,
        };
      }
      return {
        kind: "ok",
        provider: "gemini_live",
        sessionId: crypto.randomUUID(),
        token,
        model: GEMINI_LIVE_MODEL,
        url: GEMINI_LIVE_WS_URL,
      };
    });
  } catch {
    logLive("gemini_live_fetch_error", correlationId, 0);
    return {
      kind: "error",
      status: 503,
      code: "provider_unavailable",
      retryable: true,
    };
  }
}

export function parseGeminiAuthToken(body: unknown): string | null {
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }
  const name = (body as Record<string, unknown>)["name"];
  if (!isBoundedString(name, MAX_GEMINI_TOKEN_LENGTH)) return null;
  return name;
}

export function parseLiveSessionResponse(
  body: unknown
): { sessionId: string; answerSdp: string } | null {
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    return null;
  }
  const session = (body as Record<string, unknown>)["session"];
  const transport = (body as Record<string, unknown>)["transport"];
  if (
    session === null ||
    typeof session !== "object" ||
    Array.isArray(session) ||
    transport === null ||
    typeof transport !== "object" ||
    Array.isArray(transport)
  ) {
    return null;
  }
  const id = (session as Record<string, unknown>)["id"];
  const transportType = (transport as Record<string, unknown>)["type"];
  const sdp = (transport as Record<string, unknown>)["sdp"];
  if (transportType !== undefined && transportType !== "webrtc") return null;
  if (!isBoundedString(id, MAX_SESSION_ID_LENGTH)) return null;
  if (
    typeof sdp !== "string" ||
    sdp.length === 0 ||
    sdp.length > MAX_ANSWER_SDP_LENGTH
  ) {
    return null;
  }
  return { sessionId: id, answerSdp: sdp };
}

function truncate(value: string, maxLength: number): string {
  return value.length > maxLength ? value.slice(0, maxLength) : value;
}

function isBoundedString(value: unknown, maxLength: number): value is string {
  return (
    typeof value === "string" && value.length > 0 && value.length <= maxLength
  );
}

function logLive(message: string, correlationId: string, status: number): void {
  console.error(
    JSON.stringify({
      event: message,
      correlationId,
      status,
    })
  );
}

export const live = {
  LIVE_MODEL,
  LIVE_DELEGATION_MODEL,
  LIVE_SESSIONS_URL,
  LIVE_FETCH_TIMEOUT_MS,
  MAX_SDP_LENGTH,
  LIVE_REQUEST_MAX_BYTES,
  GEMINI_LIVE_MODEL,
  GEMINI_AUTH_TOKENS_URL,
  GEMINI_LIVE_WS_URL,
  liveConfigured,
  geminiLiveConfigured,
  parseLiveSessionRequest,
  parseLiveSessionResponse,
  parseGeminiAuthToken,
  createLiveSession,
};
