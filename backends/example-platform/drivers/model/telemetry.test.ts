import { expect, test } from "bun:test";
import { buildModelOperationalTelemetryEvent, emitModelTelemetrySafely } from "./telemetry";

const coordinates = {
  provider_version: "openai-compatible-v1",
  model_version: "fixture-model-v1",
  adapter_version: "fixture-adapter-v1",
  strategy_version: "fixture-strategy-v1",
  prompt_version: "fixture-prompt-v1",
  parser_schema_version: "fixture-parser-v1",
  policy_version: "fixture-policy-v1",
  retry_version: "fixture-retry-v1",
  sampling_tool_version: "fixture-sampling-v1",
  cache_format_version: "qa-model-verdict-cache-v2" as const,
};

const validEvent = () => ({
  version: "model-operational-telemetry-v1",
  stage: "provider_attempt",
  outcome: "success",
  error_code: null,
  prompt_digest: "a".repeat(64),
  coordinates,
  attempt: 1,
  duration_ms: 17,
  token_counts: { input: 11, output: 7, total: 18 },
});

test("model telemetry is exact-shaped, detached, frozen, and content safe", () => {
  const input = validEvent();
  const event = buildModelOperationalTelemetryEvent(input);
  input.token_counts.input = 999;

  expect(event.token_counts.input).toBe(11);
  expect(Object.isFrozen(event)).toBe(true);
  expect(Object.isFrozen(event.coordinates)).toBe(true);
  expect(Object.isFrozen(event.token_counts)).toBe(true);
  const encoded = JSON.stringify(event);
  for (const sentinel of ["raw prompt sentinel", "owner-secret", "evidence-secret", "provider said"])
    expect(encoded).not.toContain(sentinel);
});

test("model telemetry rejects extras, contradictions, accessors, and proxies", () => {
  expect(() => buildModelOperationalTelemetryEvent({ ...validEvent(), raw_prompt: "raw prompt sentinel" })).toThrow("invalid shape");
  expect(() => buildModelOperationalTelemetryEvent({ ...validEvent(), outcome: "failure", error_code: null })).toThrow("contradicts");
  expect(() => buildModelOperationalTelemetryEvent({ ...validEvent(), prompt_digest: "not-a-digest" })).toThrow("digest");

  let accessed = false;
  const accessor = validEvent() as Record<string, unknown>;
  Object.defineProperty(accessor, "duration_ms", { enumerable: true, get: () => { accessed = true; return 1; } });
  expect(() => buildModelOperationalTelemetryEvent(accessor)).toThrow("invalid shape");
  expect(accessed).toBe(false);

  const proxy = new Proxy(validEvent(), { ownKeys: () => { throw new Error("proxy trap ran"); } });
  expect(() => buildModelOperationalTelemetryEvent(proxy)).toThrow("invalid shape");
});

test("telemetry sink failure is isolated", async () => {
  expect(emitModelTelemetrySafely(() => { throw new Error("sink failure"); }, validEvent())).toBe(false);
  expect(emitModelTelemetrySafely(async () => { throw new Error("async sink failure"); }, validEvent())).toBe(true);
  expect(emitModelTelemetrySafely(() => { throw new Error("must not run"); }, { ...validEvent(), query: "secret" })).toBe(false);
  await Promise.resolve();
});
