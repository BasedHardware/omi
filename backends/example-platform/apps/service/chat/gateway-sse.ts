import { chatLog } from "./dev-stack-log";

export const GATEWAY_RETRY_ATTEMPTS = 3;
export const GATEWAY_RETRY_DELAYS_MS = Object.freeze([250, 1_000]);
export const MAX_GATEWAY_EVENT_BYTES = 1_048_576;

/**
 * 429 is retried on the same gateway with this same bound: 3 attempts and
 * delays 250ms then 1000ms (~1.25s extra). After that the failure is
 * `generation_rate_limited`, never a canned-gateway fallback. The bound is
 * short on purpose: a long Retry-After would freeze the chat surface.
 */

const sseDataPayloads = (event: string): readonly string[] => Object.freeze(event
  .split(/\r?\n/u)
  .filter((line) => line.startsWith("data:"))
  .map((line) => line.slice(5).trimStart()));

export const isTransientGatewayStatus = (status: number): boolean =>
  status === 429 || status === 408 || (status >= 500 && status <= 599);

export type GatewayFailureCode =
  | "generation_provider_failed"
  | "generation_timeout"
  | "generation_rate_limited";

export const gatewayFailure = (code: GatewayFailureCode) =>
  Object.freeze({ code, retryable: true });

export const failureForGatewayStatus = (
  status: number,
): Readonly<{ readonly code: GatewayFailureCode; readonly retryable: true }> =>
  gatewayFailure(
    status === 408 || status === 504
      ? "generation_timeout"
      : status === 429
        ? "generation_rate_limited"
        : "generation_provider_failed",
  );

const ownPlainObject = (value: unknown): Record<string, unknown> | null => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return null;
  return value as Record<string, unknown>;
};

export const gatewayDelta = (
  record: Record<string, unknown>,
): Record<string, unknown> | null => {
  const choices = record.choices;
  if (!Array.isArray(choices) || choices.length === 0) return null;
  const first = ownPlainObject(choices[0]);
  return ownPlainObject(first?.delta);
};

export const gatewayDeltaContent = (record: Record<string, unknown>): string | null => {
  const content = gatewayDelta(record)?.content;
  return typeof content === "string" && content.length > 0 ? content : null;
};

export const gatewayDeltaReasoning = (record: Record<string, unknown>): string | null => {
  const delta = gatewayDelta(record);
  if (delta === null) return null;
  for (const key of ["reasoning_content", "reasoning"]) {
    const value = delta[key];
    if (typeof value === "string" && value.length > 0) return value;
  }
  return null;
};

export const gatewayDeltaHasToolCalls = (record: Record<string, unknown>): boolean => {
  const calls = gatewayDelta(record)?.tool_calls;
  return Array.isArray(calls) && calls.length > 0;
};

export const gatewayUsage = (
  record: Record<string, unknown>,
  usageId: string,
): Readonly<{
  readonly usageId: string;
  readonly provider: string;
  readonly model: string;
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly totalTokens: number;
}> | null => {
  const usage = ownPlainObject(record.usage);
  if (usage === null) return null;
  const inputTokens = usage.prompt_tokens;
  const outputTokens = usage.completion_tokens;
  const totalTokens = usage.total_tokens;
  if (!Number.isSafeInteger(inputTokens) || (inputTokens as number) < 0
    || !Number.isSafeInteger(outputTokens) || (outputTokens as number) < 0
    || !Number.isSafeInteger(totalTokens)
    || totalTokens !== (inputTokens as number) + (outputTokens as number)) {
    return null;
  }
  return Object.freeze({
    usageId,
    provider: "omi-llm-gateway",
    model: "semantic-lane",
    inputTokens: inputTokens as number,
    outputTokens: outputTokens as number,
    totalTokens: totalTokens as number,
  });
};

export interface GatewaySseStats {
  readonly sawDone: boolean;
  readonly sawContent: boolean;
  readonly sawReasoning: boolean;
  readonly sawToolCalls: boolean;
  readonly frameCount: number;
  readonly firstContentMs: number | null;
  readonly firstReasoningMs: number | null;
  readonly reasoningPreambleMs: number | null;
}

export const logGatewayStreamStats = (
  generationId: string,
  attemptId: string,
  attempt: number,
  stats: GatewaySseStats,
): void => {
  if (stats.sawReasoning) {
    chatLog("info", "reasoning_preamble", {
      generationId,
      attemptId,
      attempt,
      durationMs: stats.reasoningPreambleMs ?? stats.firstContentMs,
      firstReasoningMs: stats.firstReasoningMs,
    });
  }
  if (stats.firstContentMs !== null) {
    chatLog("info", "first_content_delta", {
      generationId,
      attemptId,
      attempt,
      msSinceStart: stats.firstContentMs,
      reasoningPreambleMs: stats.reasoningPreambleMs,
    });
  }
};

export type GatewaySseOutcome =
  | { readonly kind: "records"; readonly stats: GatewaySseStats }
  | { readonly kind: "cancelled" }
  | { readonly kind: "reset" }
  | { readonly kind: "invalid" };

const emptyStats = (): {
  sawDone: boolean;
  sawContent: boolean;
  sawReasoning: boolean;
  sawToolCalls: boolean;
  frameCount: number;
  firstContentMs: number | null;
  firstReasoningMs: number | null;
  reasoningPreambleMs: number | null;
} => ({
  sawDone: false,
  sawContent: false,
  sawReasoning: false,
  sawToolCalls: false,
  frameCount: 0,
  firstContentMs: null,
  firstReasoningMs: null,
  reasoningPreambleMs: null,
});

const noteRecord = (
  stats: ReturnType<typeof emptyStats>,
  record: Record<string, unknown>,
  elapsedMs: number,
): void => {
  stats.frameCount += 1;
  if (gatewayDeltaReasoning(record) !== null && stats.firstReasoningMs === null) {
    stats.sawReasoning = true;
    stats.firstReasoningMs = elapsedMs;
  }
  if (gatewayDeltaHasToolCalls(record)) stats.sawToolCalls = true;
  if (gatewayDeltaContent(record) !== null && stats.firstContentMs === null) {
    stats.sawContent = true;
    stats.firstContentMs = elapsedMs;
    stats.reasoningPreambleMs = stats.firstReasoningMs === null
      ? 0
      : Math.max(0, elapsedMs - stats.firstReasoningMs);
  }
};

export const consumeGatewaySse = async (input: {
  readonly body: ReadableStream<Uint8Array>;
  readonly isCancelled: () => boolean;
  readonly onRecord: (record: Record<string, unknown>) => void;
  readonly startedAt: number;
  readonly now?: () => number;
  readonly allowDataAfterDone?: boolean;
}): Promise<GatewaySseOutcome> => {
  const now = input.now ?? Date.now;
  const reader = input.body.getReader();
  const decoder = new TextDecoder();
  const stats = emptyStats();
  let buffer = "";
  const dispatchEvent = (event: string): "ok" | "invalid" => {
    const data = sseDataPayloads(event).join("\n");
    if (data.length === 0) return "ok";
    if (stats.sawDone) return input.allowDataAfterDone === true ? "ok" : "invalid";
    if (data === "[DONE]") {
      stats.sawDone = true;
      stats.frameCount += 1;
      return "ok";
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(data) as unknown;
    } catch {
      return "invalid";
    }
    const record = ownPlainObject(parsed);
    if (record === null) return "invalid";
    noteRecord(stats, record, Math.max(0, now() - input.startedAt));
    input.onRecord(record);
    return "ok";
  };
  try {
    while (!input.isCancelled()) {
      const next = await reader.read();
      buffer += decoder.decode(next.value, { stream: !next.done });
      if (buffer.length > MAX_GATEWAY_EVENT_BYTES) {
        await reader.cancel().catch(() => undefined);
        return { kind: "invalid" };
      }
      const events = buffer.split(/\r?\n\r?\n/u);
      buffer = events.pop() ?? "";
      for (const event of events) {
        const dispatched = dispatchEvent(event);
        if (dispatched === "invalid") {
          await reader.cancel().catch(() => undefined);
          return { kind: "invalid" };
        }
      }
      if (next.done) {
        if (buffer.trim().length > 0) {
          const dispatched = dispatchEvent(buffer);
          buffer = "";
          if (dispatched === "invalid") return { kind: "invalid" };
        }
        break;
      }
    }
  } catch {
    if (input.isCancelled()) return { kind: "cancelled" };
    if (stats.frameCount === 0 && !stats.sawDone) return { kind: "reset" };
    return { kind: "invalid" };
  }
  if (input.isCancelled()) return { kind: "cancelled" };
  return { kind: "records", stats: Object.freeze({ ...stats }) };
};

const defaultSleep = (ms: number): Promise<void> => new Promise((resolve) => {
  setTimeout(resolve, ms);
});

const isAbortError = (error: unknown): boolean => {
  if (error === null || typeof error !== "object") return false;
  const name = (error as { name?: unknown }).name;
  return name === "AbortError";
};

export const runGatewaySseRequest = async (input: {
  readonly fetch: typeof fetch;
  readonly url: string;
  readonly init: RequestInit;
  readonly isCancelled: () => boolean;
  readonly onRecord: (record: Record<string, unknown>) => void;
  readonly generationId: string;
  readonly attemptId: string;
  readonly sleep?: (ms: number) => Promise<void>;
  readonly maxAttempts?: number;
  readonly delaysMs?: readonly number[];
  readonly now?: () => number;
  readonly allowDataAfterDone?: boolean;
  /** Retry a 200/[DONE] stream that delivered no content. Off for tool rounds. */
  readonly retryEmptyDone?: boolean;
}): Promise<
  | { readonly kind: "ok"; readonly stats: GatewaySseStats; readonly attempt: number }
  | { readonly kind: "cancelled" }
  | {
      readonly kind: "failed";
      readonly error: ReturnType<typeof gatewayFailure>;
      readonly attempt: number;
      readonly status: number | null;
    }
> => {
  const maxAttempts = input.maxAttempts ?? GATEWAY_RETRY_ATTEMPTS;
  const delays = input.delaysMs ?? GATEWAY_RETRY_DELAYS_MS;
  const sleep = input.sleep ?? defaultSleep;
  const now = input.now ?? Date.now;
  let lastStatus: number | null = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    if (input.isCancelled()) return { kind: "cancelled" };
    const startedAt = now();
    chatLog("info", "provider_request_started", {
      generationId: input.generationId,
      attemptId: input.attemptId,
      attempt,
    });
    let response: Response;
    try {
      response = await input.fetch(input.url, input.init);
    } catch (error) {
      if (input.isCancelled() || isAbortError(error)) return { kind: "cancelled" };
      chatLog("warn", "provider_attempt_failed", {
        generationId: input.generationId,
        attemptId: input.attemptId,
        attempt,
        reason: "connect_reset",
      });
      if (attempt >= maxAttempts) {
        return { kind: "failed", error: gatewayFailure("generation_provider_failed"), attempt, status: null };
      }
      await sleep(delays[attempt - 1] ?? delays.at(-1) ?? 250);
      continue;
    }
    lastStatus = response.status;
    if (!response.ok || response.body === null) {
      const transient = isTransientGatewayStatus(response.status);
      chatLog(transient ? "warn" : "error", "provider_attempt_failed", {
        generationId: input.generationId,
        attemptId: input.attemptId,
        attempt,
        status: response.status,
        reason: transient ? (response.status === 429 ? "http_429" : "http_5xx") : "http_4xx",
      });
      try {
        await response.body?.cancel();
      } catch {
        // Best-effort drain; the next attempt must not wait on this body.
      }
      if (!transient || attempt >= maxAttempts) {
        return {
          kind: "failed",
          error: failureForGatewayStatus(response.status),
          attempt,
          status: response.status,
        };
      }
      await sleep(delays[attempt - 1] ?? delays.at(-1) ?? 250);
      continue;
    }
    const outcome = await consumeGatewaySse({
      body: response.body,
      isCancelled: input.isCancelled,
      onRecord: input.onRecord,
      startedAt,
      now,
      allowDataAfterDone: input.allowDataAfterDone,
    });
    if (outcome.kind === "cancelled") return { kind: "cancelled" };
    if (outcome.kind === "reset") {
      chatLog("warn", "provider_attempt_failed", {
        generationId: input.generationId,
        attemptId: input.attemptId,
        attempt,
        reason: "connect_reset",
      });
      if (attempt >= maxAttempts) {
        return {
          kind: "failed",
          error: gatewayFailure("generation_provider_failed"),
          attempt,
          status: response.status,
        };
      }
      await sleep(delays[attempt - 1] ?? delays.at(-1) ?? 250);
      continue;
    }
    if (outcome.kind === "invalid") {
      return {
        kind: "failed",
        error: gatewayFailure("generation_provider_failed"),
        attempt,
        status: response.status,
      };
    }
    logGatewayStreamStats(input.generationId, input.attemptId, attempt, outcome.stats);
    if (input.retryEmptyDone === true && !outcome.stats.sawContent && !outcome.stats.sawToolCalls) {
      chatLog("warn", "provider_attempt_failed", {
        generationId: input.generationId,
        attemptId: input.attemptId,
        attempt,
        reason: "empty_done",
        sawDone: outcome.stats.sawDone,
        sawReasoning: outcome.stats.sawReasoning,
      });
      if (attempt >= maxAttempts) {
        return {
          kind: "failed",
          error: gatewayFailure("generation_provider_failed"),
          attempt,
          status: response.status,
        };
      }
      await sleep(delays[attempt - 1] ?? delays.at(-1) ?? 250);
      continue;
    }
    return { kind: "ok", stats: outcome.stats, attempt };
  }
  return {
    kind: "failed",
    error: lastStatus === null
      ? gatewayFailure("generation_provider_failed")
      : failureForGatewayStatus(lastStatus),
    attempt: maxAttempts,
    status: lastStatus,
  };
};
