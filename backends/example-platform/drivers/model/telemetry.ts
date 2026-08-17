import { isProxy } from "node:util/types";
import type { ModelPromptCoordinates } from "./port";

export type ModelTelemetryStage = "provider_attempt";
export type ModelTelemetryOutcome = "success" | "failure";
export type ModelTelemetryErrorCode = "rate_limited" | "timeout" | "provider_error" | "invalid_response" | "unknown";

export interface ModelOperationalTelemetryEvent {
  readonly version: "model-operational-telemetry-v1";
  readonly stage: ModelTelemetryStage;
  readonly outcome: ModelTelemetryOutcome;
  readonly error_code: ModelTelemetryErrorCode | null;
  readonly prompt_digest: string | null;
  readonly coordinates: ModelPromptCoordinates;
  readonly attempt: number;
  readonly duration_ms: number;
  /** Provider-reported counters; `total` is retained as independently reported. */
  readonly token_counts: Readonly<{ input: number; output: number; total: number }>;
}

export type ModelTelemetrySink = (event: ModelOperationalTelemetryEvent) => void | Promise<void>;

const VERSION = /^[A-Za-z0-9._:-]{1,160}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const COORDINATE_KEYS = [
  "provider_version", "model_version", "adapter_version", "strategy_version",
  "prompt_version", "parser_schema_version", "policy_version", "retry_version",
  "sampling_tool_version", "cache_format_version",
] as const;

const exactKeys = (value: object, expected: readonly string[]): boolean => {
  const actual = Reflect.ownKeys(value);
  return actual.length === expected.length
    && actual.every((key) => typeof key === "string" && expected.includes(key));
};

const plainRecord = (value: unknown): value is Record<string, unknown> => {
  if (typeof value !== "object" || value === null || Array.isArray(value) || isProxy(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) return false;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  return Reflect.ownKeys(descriptors).every((key) => typeof key === "string"
    && descriptors[key]?.enumerable === true
    && Object.hasOwn(descriptors[key]!, "value"));
};

const boundedInteger = (value: unknown, maximum: number): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;

const parseCoordinates = (value: unknown): ModelPromptCoordinates => {
  if (!plainRecord(value) || !exactKeys(value, COORDINATE_KEYS)) throw new TypeError("model telemetry coordinates have an invalid shape");
  for (const key of COORDINATE_KEYS) {
    if (key === "cache_format_version") continue;
    if (typeof value[key] !== "string" || !VERSION.test(value[key])) throw new TypeError("model telemetry coordinates have invalid values");
  }
  if (value.cache_format_version !== "qa-model-verdict-cache-v2") throw new TypeError("model telemetry coordinates have invalid values");
  return Object.freeze({
    provider_version: value.provider_version as string,
    model_version: value.model_version as string,
    adapter_version: value.adapter_version as string,
    strategy_version: value.strategy_version as string,
    prompt_version: value.prompt_version as string,
    parser_schema_version: value.parser_schema_version as string,
    policy_version: value.policy_version as string,
    retry_version: value.retry_version as string,
    sampling_tool_version: value.sampling_tool_version as string,
    cache_format_version: "qa-model-verdict-cache-v2",
  });
};

/** Exact-shaped, content-free event builder. No caller-owned object survives. */
export const buildModelOperationalTelemetryEvent = (input: unknown): ModelOperationalTelemetryEvent => {
  const keys = ["version", "stage", "outcome", "error_code", "prompt_digest", "coordinates", "attempt", "duration_ms", "token_counts"];
  if (!plainRecord(input) || !exactKeys(input, keys)) throw new TypeError("model telemetry event has an invalid shape");
  if (input.version !== "model-operational-telemetry-v1" || input.stage !== "provider_attempt"
    || (input.outcome !== "success" && input.outcome !== "failure")) throw new TypeError("model telemetry event has invalid values");
  const allowedErrors = new Set<ModelTelemetryErrorCode>(["rate_limited", "timeout", "provider_error", "invalid_response", "unknown"]);
  if (input.outcome === "success" ? input.error_code !== null : typeof input.error_code !== "string" || !allowedErrors.has(input.error_code as ModelTelemetryErrorCode)) {
    throw new TypeError("model telemetry outcome contradicts its error code");
  }
  if (input.prompt_digest !== null && (typeof input.prompt_digest !== "string" || !DIGEST.test(input.prompt_digest))) throw new TypeError("model telemetry prompt digest is invalid");
  if (!boundedInteger(input.attempt, 16) || input.attempt < 1 || !boundedInteger(input.duration_ms, 86_400_000)) throw new TypeError("model telemetry counters are invalid");
  if (!plainRecord(input.token_counts) || !exactKeys(input.token_counts, ["input", "output", "total"])
    || !boundedInteger(input.token_counts.input, 1_000_000_000) || !boundedInteger(input.token_counts.output, 1_000_000_000)
    || !boundedInteger(input.token_counts.total, 2_000_000_000)) throw new TypeError("model telemetry token counts are invalid");
  const token_counts = Object.freeze({ input: input.token_counts.input, output: input.token_counts.output, total: input.token_counts.total });
  return Object.freeze({
    version: "model-operational-telemetry-v1",
    stage: "provider_attempt",
    outcome: input.outcome,
    error_code: input.error_code as ModelTelemetryErrorCode | null,
    prompt_digest: input.prompt_digest as string | null,
    coordinates: parseCoordinates(input.coordinates),
    attempt: input.attempt,
    duration_ms: input.duration_ms,
    token_counts,
  });
};

/** Telemetry failure and rejection are isolated from model behavior. */
export const emitModelTelemetrySafely = (sink: ModelTelemetrySink | undefined, input: unknown): boolean => {
  if (!sink) return false;
  let event: ModelOperationalTelemetryEvent;
  try { event = buildModelOperationalTelemetryEvent(input); } catch { return false; }
  try {
    const result = sink(event);
    if (result && typeof (result as Promise<void>).then === "function") void Promise.resolve(result).catch(() => {});
    return true;
  } catch {
    return false;
  }
};
