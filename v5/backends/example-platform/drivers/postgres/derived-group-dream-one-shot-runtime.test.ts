import { describe, expect, test } from "bun:test";

import {
  DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
} from "../../apps/service/workers/derived-group-dream-contract";
import {
  defineModelPipelineExclusivity,
  MODEL_PIPELINE_RESOURCE_VERSION,
} from "../../apps/service/workers/model-pipeline-exclusivity";
import {
  bindModelPipelineResourceAdmission,
  defineModelPipelineResourceAdmission,
} from "../../apps/service/workers/model-pipeline-resource-admission";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import type { PostgresTransactionPool } from "./connection";
import {
  createPostgresDerivedGroupDreamOneShotRuntime,
} from "./derived-group-dream-one-shot-runtime";

const digest = (character: string): string => character.repeat(64);

const strategy = registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: "strategy:dream:one-shot:test",
  work_kind: "derived_group_dream",
  coordinates: {
    strategy_version: "derived-group-dream:v1",
    model_version: "none",
    prompt_version: "none",
    policy_version: "dream-policy:test",
    code_version: "derived-group-dream:v1",
    schema_version: "derived-group-dream-response:v1",
    tokenizer_version: "none",
    tool_version: "none",
    result_contract_version: DERIVED_GROUP_DREAM_RESULT_CONTRACT_VERSION,
    speaker_strategy_version: "none",
    boundary_strategy_version: "none",
  },
});

const unusedPool: PostgresTransactionPool = Object.freeze({
  withTransaction: async () => { throw new Error("construction must not touch the database"); },
});

const resourceDigest = digest("b");
const exclusivity = bindModelPipelineResourceAdmission(
  defineModelPipelineExclusivity(async (_resource, callback) =>
    Object.freeze({ kind: "completed" as const, value: await callback(new AbortController().signal) })),
  defineModelPipelineResourceAdmission([{ resource_digest: resourceDigest, max_concurrency: 1 }]),
);
const pipeline = {
  model_pipeline_exclusivity: exclusivity,
  resolve_model_pipeline_resource: async () => Object.freeze({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: resourceDigest,
  }),
};

describe("PostgreSQL derived-group-dream one-shot runtime", () => {
  test("constructs inertly and exposes only bounded operations", () => {
    const runtime = createPostgresDerivedGroupDreamOneShotRuntime({
      pool: unusedPool,
      strategies: [strategy],
      ...pipeline,
      max_parent_rematerializations: 2,
    });
    expect(Object.keys(runtime)).toEqual(["accept", "runNext", "recoverExpired"]);
    expect(typeof runtime.accept).toBe("function");
    expect(typeof runtime.runNext).toBe("function");
    expect(typeof runtime.recoverExpired).toBe("function");
  });

  test("accepts no model resolver, so no serving default can be smuggled in", () => {
    const runtime = createPostgresDerivedGroupDreamOneShotRuntime({
      pool: unusedPool,
      strategies: [strategy],
      ...pipeline,
      max_parent_rematerializations: 2,
    });
    // The dream planner is deterministic. A resolve_model option would be the
    // seam a serving-model default could enter through; it does not exist.
    expect("resolve_model" in runtime).toBe(false);
  });

  test("rejects empty, non-dream, duplicate-contract, and invalid retry configuration", () => {
    const construct = (strategies: readonly typeof strategy[], retries = 2) =>
      createPostgresDerivedGroupDreamOneShotRuntime({
        pool: unusedPool,
        strategies,
        ...pipeline,
        max_parent_rematerializations: retries,
      });
    expect(() => construct([])).toThrow("invalid_strategy_registry");
    expect(() => construct([strategy, strategy])).toThrow("invalid_strategy_registry");
    expect(() => construct([strategy], 0)).toThrow("invalid_parent_retry_bound");
    expect(() => createPostgresDerivedGroupDreamOneShotRuntime({
      pool: unusedPool,
      strategies: [strategy],
      model_pipeline_exclusivity: {} as never,
      resolve_model_pipeline_resource: pipeline.resolve_model_pipeline_resource,
      max_parent_rematerializations: 2,
    })).toThrow("invalid_port");

    const predicate = registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION,
      strategy_id: "strategy:predicate:test",
      work_kind: "predicate_batch",
      coordinates: strategy.coordinates,
    });
    expect(() => construct([predicate as never])).toThrow("invalid_strategy_registry");
  });

  test("rejects a proxied model pipeline resource resolver", () => {
    expect(() => createPostgresDerivedGroupDreamOneShotRuntime({
      pool: unusedPool,
      strategies: [strategy],
      model_pipeline_exclusivity: exclusivity,
      resolve_model_pipeline_resource: new Proxy(
        pipeline.resolve_model_pipeline_resource, {},
      ),
      max_parent_rematerializations: 2,
    })).toThrow("invalid_model_pipeline_resource_resolver");
  });
});
