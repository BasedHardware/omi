import { withTimeout } from "./wire";

// GPT-Live-1 session creation. The Worker is the only place the project API
// key lives: clients POST an SDP offer, the Worker exchanges it for an SDP
// answer with OpenAI, and returns only the answer plus the opaque session id.
export const LIVE_MODEL = "gpt-live-1";
// Responses delegation backend model, matching the OpenAI GPT-Live docs
// example. This is an OpenAI model id, not the OpenRouter chat pin.
export const LIVE_DELEGATION_MODEL = "gpt-5.6-terra";
// Official OpenAI API host only. Do not accept lookalikes, proxies, or http.
export const LIVE_SESSIONS_URL = "https://api.openai.com/v1/live/sessions";
export const LIVE_FETCH_TIMEOUT_MS = 20_000;
export const MAX_SDP_LENGTH = 262_144;
const MAX_SESSION_ID_LENGTH = 256;
const MAX_ANSWER_SDP_LENGTH = 1_048_576;
const MAX_INSTRUCTIONS_LENGTH = 4_096;

export const LIVE_INSTRUCTIONS =
  "You are Omi, a concise and helpful personal assistant. Keep spoken replies short. When a request needs current facts, tools, or the user's saved context, delegate it to the backend and speak the result when it is ready.";

export const LIVE_DELEGATION_INSTRUCTIONS =
  "Use the Omi backend to look up the user's saved context. When current facts are needed, use web search. Return concise, grounded results for a spoken conversation.";

export type LiveEnv = {
  OPENAI_API_KEY?: string;
};

export const LIVE_REQUEST_MAX_BYTES = 262_144;

export const liveConfigured = (env: LiveEnv): boolean =>
  typeof env.OPENAI_API_KEY === "string" && env.OPENAI_API_KEY.length > 0;

export type LiveSessionRequest = { sdp: string };

export const parseLiveSessionRequest = (
  value: unknown
): LiveSessionRequest | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const sdp = (value as Record<string, unknown>)["sdp"];
  if (!isBoundedString(sdp, MAX_SDP_LENGTH)) return null;
  return { sdp };
};

export type LiveSessionResult =
  | { kind: "ok"; sessionId: string; answerSdp: string }
  | { kind: "error"; status: number; code: string; retryable: boolean };

export const createLiveSession = async (
  env: LiveEnv,
  request: LiveSessionRequest,
  correlationId: string
): Promise<LiveSessionResult> => {
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
          transport: { type: "webrtc", sdp: request.sdp },
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
      return { kind: "ok", ...parsed };
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
};

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
  liveConfigured,
  parseLiveSessionRequest,
  parseLiveSessionResponse,
  createLiveSession,
};
