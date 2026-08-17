import { expect, test } from "bun:test";

import { createChatGenerationSupervisor } from "./generation-supervisor";
import {
  REAL_MODEL_GENERATION_LIVENESS,
  resolveDevGenerationLiveness,
} from "./real-model-liveness";

test("only an explicit real-model run moves the generation deadlines", () => {
  expect(resolveDevGenerationLiveness(undefined)).toBeNull();
  expect(resolveDevGenerationLiveness("")).toBeNull();
  expect(resolveDevGenerationLiveness("test")).toBeNull();
  expect(resolveDevGenerationLiveness("real")).toBe(REAL_MODEL_GENERATION_LIVENESS);
  expect(resolveDevGenerationLiveness("  real  ")).toBe(REAL_MODEL_GENERATION_LIVENESS);
});

test("the real-model policy outlasts a reasoning preamble the default kills", () => {
  // The measured failure: GLM-4.7 spent ~26s and 280 reasoning tokens before
  // its first content delta. The default policy caps a whole run at 1s.
  const measuredFirstContentMs = 26_000;
  expect(REAL_MODEL_GENERATION_LIVENESS.firstEventDeadlineMs).toBeGreaterThan(measuredFirstContentMs);
  expect(REAL_MODEL_GENERATION_LIVENESS.maxRunDurationMs)
    .toBeGreaterThan(REAL_MODEL_GENERATION_LIVENESS.firstEventDeadlineMs);
});

test("the supervisor accepts the real-model policy as valid", () => {
  // validateLivenessPolicy throws on out-of-bounds deadlines; constructing a
  // supervisor with this policy is the check that it stays inside them.
  expect(() =>
    createChatGenerationSupervisor({
      source: {
        start: () => ({ cancel: () => {} }),
      } as never,
      events: {
        append: () => {},
        listAfter: () => [],
        readLifecycle: () => null,
      } as never,
      finalization: { finalize: () => {} } as never,
      liveness: REAL_MODEL_GENERATION_LIVENESS,
    } as never)).not.toThrow();
});
