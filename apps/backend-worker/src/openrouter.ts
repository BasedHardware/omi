import { gatewayFailureEvent } from "./observability";

const SYSTEM_PROMPT = "You are Omi, a concise and helpful personal assistant.";
const MAX_TOKENS = 768;
const MAX_RESPONSE_TEXT = 32_768;
const MAX_URL_LENGTH = 2048;
const MAX_MODEL_LENGTH = 128;
const ENABLED_TRUE = "true";

// Official OpenRouter API host only. Do not accept lookalikes, proxies, or http.
export const OPENROUTER_GATEWAY_HOST = "openrouter.ai";
// Hung upstream must not stall a Durable Object alarm.
export const GATEWAY_FETCH_TIMEOUT_MS = 15_000;

// The deployment is intentionally pinned rather than accepting arbitrary
// OpenRouter model identifiers from configuration. A model change is a code
// review + evaluation event, not an operational typo with unknown behavior/cost.
export const LUNA_MODEL = "openai/gpt-5.6-luna";

export type GatewayConfig = {
  url: string;
  model: string;
  secret: string;
};

export type GatewayEnv = {
  OPENROUTER_GATEWAY_ENABLED: string | undefined;
  OPENROUTER_GATEWAY_URL: string | undefined;
  OPENROUTER_API_KEY: string | undefined;
  OPENROUTER_MODEL: string | undefined;
};

export type GatewaySecretEnv = {
  OPENROUTER_GATEWAY_URL: string;
  OPENROUTER_API_KEY: string;
};

export type GatewayResult = { kind: "ok"; text: string } | { kind: "error" };

export const gatewayModeEnabled = (env: GatewayEnv): boolean =>
  env.OPENROUTER_GATEWAY_ENABLED === ENABLED_TRUE;

export const gatewayConfig = (env: GatewayEnv): GatewayConfig | null => {
  const url = env.OPENROUTER_GATEWAY_URL ?? "";
  const secret = env.OPENROUTER_API_KEY ?? "";
  const model = env.OPENROUTER_MODEL ?? "";
  if (!isValidGatewayUrl(url)) return null;
  if (secret.length === 0) return null;
  if (!isBoundedString(model, MAX_MODEL_LENGTH)) return null;
  if (model !== LUNA_MODEL) return null;
  return { url, model, secret };
};

export const gatewayReady = (env: GatewayEnv): boolean =>
  gatewayModeEnabled(env) && gatewayConfig(env) !== null;

export const generateViaGateway = async (
  config: GatewayConfig,
  prompt: string,
  correlationId: string
): Promise<GatewayResult> => {
  try {
    const response = await fetch(config.url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${config.secret}`,
        "x-omi-correlation-id": correlationId,
      },
      body: JSON.stringify({
        model: config.model,
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          { role: "user", content: prompt },
        ],
        max_tokens: MAX_TOKENS,
      }),
      signal: AbortSignal.timeout(GATEWAY_FETCH_TIMEOUT_MS),
    });
    if (!response.ok) {
      logGateway(
        "gateway_http_error",
        correlationId,
        config.model,
        response.status
      );
      return { kind: "error" };
    }
    const text = extractText(await response.json());
    if (text === null) {
      logGateway(
        "gateway_shape_error",
        correlationId,
        config.model,
        response.status
      );
      return { kind: "error" };
    }
    return { kind: "ok", text };
  } catch {
    logGateway("gateway_fetch_error", correlationId, config.model, 0);
    return { kind: "error" };
  }
};

function extractText(body: unknown): string | null {
  if (body === null || typeof body !== "object") return null;
  const choices = (body as Record<string, unknown>)["choices"];
  if (!Array.isArray(choices) || choices.length === 0) return null;
  const first = choices[0];
  if (first === null || typeof first !== "object") return null;
  const message = (first as Record<string, unknown>)["message"];
  if (message === null || typeof message !== "object") return null;
  const content = (message as Record<string, unknown>)["content"];
  if (typeof content !== "string" || content.length === 0) return null;
  return content.length > MAX_RESPONSE_TEXT
    ? content.slice(0, MAX_RESPONSE_TEXT)
    : content;
}

function isValidGatewayUrl(value: string): boolean {
  if (!isBoundedString(value, MAX_URL_LENGTH)) return false;
  try {
    const parsed = new URL(value);
    return (
      parsed.protocol === "https:" &&
      parsed.hostname.toLowerCase() === OPENROUTER_GATEWAY_HOST
    );
  } catch {
    return false;
  }
}

function isBoundedString(value: unknown, maxLength: number): value is string {
  return (
    typeof value === "string" && value.length > 0 && value.length <= maxLength
  );
}

function logGateway(
  message: string,
  correlationId: string,
  model: string,
  status: number
): void {
  console.error(
    JSON.stringify(
      gatewayFailureEvent({ message, correlationId, model, status })
    )
  );
}

export const openrouter = {
  LUNA_MODEL,
  OPENROUTER_GATEWAY_HOST,
  GATEWAY_FETCH_TIMEOUT_MS,
  gatewayModeEnabled,
  gatewayConfig,
  gatewayReady,
  generateViaGateway,
};
