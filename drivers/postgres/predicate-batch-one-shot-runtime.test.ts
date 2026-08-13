import { describe, expect, test } from "bun:test";

import { DURABLE_MEMORY_GRAPH_PLAN_VERSION } from
  "../../apps/service/workers/durable-memory-graph-plan";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresPredicateBatchOneShotRuntime } from "./predicate-batch-one-shot-runtime";
import {
  defineModelPipelineExclusivity,
  MODEL_PIPELINE_RESOURCE_VERSION,
} from "../../apps/service/workers/model-pipeline-exclusivity";
import {
  bindModelPipelineResourceAdmission,
  defineModelPipelineResourceAdmission,
} from "../../apps/service/workers/model-pipeline-resource-admission";

const strategy = registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: "strategy:predicate:one-shot:test",
  work_kind: "predicate_batch",
  coordinates: {
    strategy_version: "predicate-alignment-v3",
    model_version: "fake:test:v1",
    prompt_version: "predicate-prompt-v2",
    policy_version: "predicate-policy-v1",
    code_version: "relations-exhaustive-v3",
    schema_version: "predicate-response-v2",
    tokenizer_version: "none",
    tool_version: "none",
    result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
    speaker_strategy_version: "none",
    boundary_strategy_version: "none",
  },
});

const unusedPool: PostgresTransactionPool = Object.freeze({
  withTransaction: async () => { throw new Error("constructor_must_not_open_postgres"); },
});
const resourceDigest = "b".repeat(64);
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

describe("PostgreSQL predicate-batch one-shot runtime", () => {
  test("constructs inertly and exposes only bounded operations", () => {
    const runtime = createPostgresPredicateBatchOneShotRuntime({
      pool: unusedPool,
      strategies: [strategy],
      resolve_model: async () => null,
      ...pipeline,
      max_parent_rematerializations: 2,
    });
    expect(Object.keys(runtime)).toEqual(["schedule", "runNext", "recoverExpired"]);
    expect(typeof runtime.schedule).toBe("function");
    expect(typeof runtime.runNext).toBe("function");
    expect(typeof runtime.recoverExpired).toBe("function");
  });

  test("rejects empty, non-predicate, duplicate-contract, and invalid retry configuration", () => {
    const construct = (strategies: readonly typeof strategy[], retries = 2) =>
      createPostgresPredicateBatchOneShotRuntime({
        pool: unusedPool,
        strategies,
        resolve_model: async () => null,
        ...pipeline,
        max_parent_rematerializations: retries,
      });
    expect(() => construct([])).toThrow("invalid_strategy_registry");
    expect(() => construct([strategy, strategy])).toThrow("invalid_strategy_registry");
    expect(() => construct([strategy], 0)).toThrow("invalid_parent_retry_bound");
    expect(() => createPostgresPredicateBatchOneShotRuntime({
      pool: unusedPool, strategies: [strategy], resolve_model: async () => null,
      model_pipeline_exclusivity: {} as never,
      resolve_model_pipeline_resource: pipeline.resolve_model_pipeline_resource,
      max_parent_rematerializations: 2,
    })).toThrow("invalid_port");
    const retrieval = registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION,
      strategy_id: "strategy:retrieval:test",
      work_kind: "retrieval",
      coordinates: strategy.coordinates,
    });
    expect(() => construct([retrieval as never])).toThrow("invalid_strategy_registry");
  });
});
