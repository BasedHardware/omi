import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../core/consolidate/strategy-assignment";
import {
  DURABLE_MEMORY_GRAPH_PLAN_VERSION,
} from "../../apps/service/workers/durable-memory-graph-plan";
import {
  GROUNDED_EXTRACTION_PROMPT_VERSION,
  GROUNDED_MENTION_STRATEGY_VERSION,
} from "../../core/extract/grounded";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresFormationOneShotRuntime } from "./formation-one-shot-runtime";
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
  strategy_id: "strategy:formation:one-shot:test",
  work_kind: "formation",
  coordinates: {
    strategy_version: "formation:test:v1",
    model_version: "fake:test:v1",
    prompt_version: GROUNDED_EXTRACTION_PROMPT_VERSION,
    policy_version: "policy:test:v1",
    code_version: "code:test:v1",
    schema_version: "schema:test:v1",
    tokenizer_version: "none",
    tool_version: "none",
    result_contract_version: DURABLE_MEMORY_GRAPH_PLAN_VERSION,
    speaker_strategy_version: GROUNDED_MENTION_STRATEGY_VERSION,
    boundary_strategy_version: "v4",
  },
});

const unusedPool: PostgresTransactionPool = Object.freeze({
  withTransaction: async () => {
    throw new Error("constructor_must_not_open_postgres");
  },
});
const resourceDigest = "a".repeat(64);
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

describe("PostgreSQL formation one-shot runtime", () => {
  test("constructs inertly and exposes only bounded operations", () => {
    const runtime = createPostgresFormationOneShotRuntime({
      pool: unusedPool,
      strategies: [strategy],
      resolve_model: async () => null,
      ...pipeline,
      max_parent_rematerializations: 2,
    });

    expect(Object.keys(runtime)).toEqual(["accept", "runNext", "recoverExpired"]);
    expect(typeof runtime.accept).toBe("function");
    expect(typeof runtime.runNext).toBe("function");
    expect(typeof runtime.recoverExpired).toBe("function");
  });

  test("rejects empty, non-formation, duplicate-contract, and invalid retry configuration", () => {
    const construct = (strategies: readonly typeof strategy[], retries = 2) =>
      createPostgresFormationOneShotRuntime({
        pool: unusedPool,
        strategies,
        resolve_model: async () => null,
        ...pipeline,
        max_parent_rematerializations: retries,
      });

    expect(() => construct([])).toThrow("invalid_strategy_registry");
    expect(() => construct([strategy, strategy])).toThrow("invalid_strategy_registry");
    expect(() => construct([strategy], 0)).toThrow("invalid_parent_retry_bound");
    expect(() => createPostgresFormationOneShotRuntime({
      pool: unusedPool, strategies: [strategy], resolve_model: async () => null,
      model_pipeline_exclusivity: {} as never,
      resolve_model_pipeline_resource: pipeline.resolve_model_pipeline_resource,
      max_parent_rematerializations: 2,
    })).toThrow("invalid_port");
    expect(() => createPostgresFormationOneShotRuntime({
      pool: unusedPool, strategies: [strategy], resolve_model: async () => null,
      model_pipeline_exclusivity: defineModelPipelineExclusivity(async (_resource, callback) =>
        Object.freeze({
          kind: "completed" as const,
          value: await callback(new AbortController().signal),
        })) as never,
      resolve_model_pipeline_resource: pipeline.resolve_model_pipeline_resource,
      max_parent_rematerializations: 2,
    })).toThrow("invalid_admitted_exclusivity");

    const retrieval = registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION,
      strategy_id: "strategy:retrieval:test",
      work_kind: "retrieval",
      coordinates: strategy.coordinates,
    });
    expect(() => construct([retrieval as never])).toThrow("invalid_strategy_registry");
  });
});
