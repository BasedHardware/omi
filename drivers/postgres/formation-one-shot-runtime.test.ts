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

describe("PostgreSQL formation one-shot runtime", () => {
  test("constructs inertly and exposes only bounded operations", () => {
    const runtime = createPostgresFormationOneShotRuntime({
      pool: unusedPool,
      strategies: [strategy],
      resolve_model: async () => null,
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
        max_parent_rematerializations: retries,
      });

    expect(() => construct([])).toThrow("invalid_strategy_registry");
    expect(() => construct([strategy, strategy])).toThrow("invalid_strategy_registry");
    expect(() => construct([strategy], 0)).toThrow("invalid_parent_retry_bound");

    const retrieval = registerMemoryStrategy({
      version: MEMORY_STRATEGY_VERSION,
      strategy_id: "strategy:retrieval:test",
      work_kind: "retrieval",
      coordinates: strategy.coordinates,
    });
    expect(() => construct([retrieval as never])).toThrow("invalid_strategy_registry");
  });
});
