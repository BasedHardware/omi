import { describe, expect, test } from "bun:test";

import {
  defineModelPipelineExclusivity,
  MODEL_PIPELINE_RESOURCE_VERSION,
} from "./model-pipeline-exclusivity";
import {
  assertAdmittedModelPipelineExclusivity,
  assertModelPipelineResourceAdmission,
  bindModelPipelineResourceAdmission,
  defineModelPipelineResourceAdmission,
} from "./model-pipeline-resource-admission";

const digest = (character: string): string => character.repeat(64);
const entry = (character: string) => Object.freeze({
  resource_digest: digest(character),
  max_concurrency: 1 as const,
});

describe("manifest-backed model pipeline resource admission", () => {
  test("admits only an exact declared opaque resource", () => {
    const admission = defineModelPipelineResourceAdmission([entry("1"), entry("2")]);
    expect(admission.admit({
      version: MODEL_PIPELINE_RESOURCE_VERSION,
      resource_digest: digest("1"),
    })).toEqual({ version: MODEL_PIPELINE_RESOURCE_VERSION, resource_digest: digest("1") });
    expect(admission.admit({
      version: MODEL_PIPELINE_RESOURCE_VERSION,
      resource_digest: digest("3"),
    })).toBeNull();
    expect(assertModelPipelineResourceAdmission(admission)).toBe(admission);
  });

  test("rejects duplicates, ordering drift, raw keys, unsupported capacity, and hostile rows", () => {
    for (const entries of [
      [entry("2"), entry("1")],
      [entry("1"), entry("1")],
      [{ resource_digest: "raw-api-key", max_concurrency: 1 }],
      [{ resource_digest: digest("1"), max_concurrency: 2 }],
    ]) expect(() => defineModelPipelineResourceAdmission(entries as never)).toThrow("invalid_manifest");
    let getterCalls = 0;
    const hostile = Object.defineProperties({}, {
      resource_digest: { enumerable: true, get() { getterCalls += 1; return digest("1"); } },
      max_concurrency: { enumerable: true, value: 1 },
    });
    expect(() => defineModelPipelineResourceAdmission([hostile] as never)).toThrow("invalid_manifest");
    expect(getterCalls).toBe(0);
    expect(() => assertModelPipelineResourceAdmission({})).toThrow("invalid_port");
  });

  test("brands only a resource-admitted exclusivity port and closes unknown resources pre-callback", async () => {
    let calls = 0;
    const generic = defineModelPipelineExclusivity(async (_resource, callback) => {
      calls += 1;
      return Object.freeze({
        kind: "completed" as const,
        value: await callback(new AbortController().signal),
      });
    });
    expect(() => assertAdmittedModelPipelineExclusivity(generic))
      .toThrow("invalid_admitted_exclusivity");
    const admitted = bindModelPipelineResourceAdmission(
      generic,
      defineModelPipelineResourceAdmission([entry("1")]),
    );
    expect(assertAdmittedModelPipelineExclusivity(admitted)).toBe(admitted);
    await expect(admitted.runExclusive({
      version: MODEL_PIPELINE_RESOURCE_VERSION,
      resource_digest: digest("2"),
    }, async () => "must not run")).resolves.toEqual({ kind: "unavailable" });
    expect(calls).toBe(0);
  });
});
