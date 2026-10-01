import { describe, expect, test } from "bun:test";

import {
  defineModelPipelineExclusivity,
} from "../workers/model-pipeline-exclusivity";
import {
  bindModelPipelineResourceAdmission,
  defineModelPipelineResourceAdmission,
} from "../workers/model-pipeline-resource-admission";
import { composeProductionProcessModelLocks } from "./production-process-locks";

const digest = (character: string): string => character.repeat(64);

describe("production process model locks", () => {
  test("binds opaque qualification-manifest resources and never names serving models", async () => {
    const source = await Bun.file(new URL("./production-process-locks.ts", import.meta.url)).text();
    expect(source).not.toMatch(/deepseek/i);
    expect(source).not.toMatch(/\bglm\b/i);
    const admission = defineModelPipelineResourceAdmission([
      Object.freeze({ resource_digest: digest("1"), max_concurrency: 1 as const }),
      Object.freeze({ resource_digest: digest("2"), max_concurrency: 1 as const }),
    ]);
    const exclusivity = defineModelPipelineExclusivity(async (_resource, callback) =>
      Object.freeze({ kind: "completed" as const, value: await callback(new AbortController().signal) }));
    const admitted = bindModelPipelineResourceAdmission(exclusivity, admission);
    expect(composeProductionProcessModelLocks([digest("1"), digest("2")], admitted)).toBe(admitted);
    expect(() => composeProductionProcessModelLocks([], admitted)).toThrow("missing_resources");
  });
});
