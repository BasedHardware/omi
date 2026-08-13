import { describe, expect, test } from "bun:test";

import { createPostgresMemoryQueryEvaluationOneShotRuntime } from
  "./memory-query-evaluation-one-shot-runtime";
import type { PostgresTransactionPool } from "./connection";
import {
  defineModelPipelineExclusivity,
  MODEL_PIPELINE_RESOURCE_VERSION,
} from "../../apps/service/workers/model-pipeline-exclusivity";

const unusedPool: PostgresTransactionPool = Object.freeze({
  withTransaction: async () => { throw new Error("constructor_must_not_open_postgres"); },
});

const pipelineOptions = () => ({
  model_pipeline_exclusivity: defineModelPipelineExclusivity(async (_resource, callback) =>
    Object.freeze({ kind: "completed" as const, value: await callback(new AbortController().signal) })),
  resolve_model_pipeline_resource: async () => Object.freeze({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: "b".repeat(64),
  }),
});

describe("PostgreSQL query-evaluation one-shot runtime", () => {
  test("constructs inertly and exposes only bounded stage and run operations", () => {
    const runtime = createPostgresMemoryQueryEvaluationOneShotRuntime({
      pool: unusedPool,
      codec_root_secret: new Uint8Array(32).fill(7),
      produce: async () => { throw new Error("model_must_not_run_at_construction"); },
      ...pipelineOptions(),
    });
    expect(Object.keys(runtime)).toEqual(["stageInput", "run"]);
    expect(typeof runtime.stageInput).toBe("function");
    expect(typeof runtime.run).toBe("function");
  });

  test("rejects invalid codec roots before opening PostgreSQL", () => {
    expect(() => createPostgresMemoryQueryEvaluationOneShotRuntime({
      pool: unusedPool,
      codec_root_secret: new Uint8Array(31),
      produce: async () => { throw new Error("unused"); },
      ...pipelineOptions(),
    })).toThrow("invalid_config");
  });

  test("rejects a hostile stage body before opening PostgreSQL", async () => {
    let getterCalls = 0;
    const runtime = createPostgresMemoryQueryEvaluationOneShotRuntime({
      pool: unusedPool,
      codec_root_secret: new Uint8Array(32).fill(7),
      produce: async () => { throw new Error("unused"); },
      ...pipelineOptions(),
    });
    const body = Object.defineProperties({}, {
      input_ref: { enumerable: true, get() { getterCalls += 1; return "hidden"; } },
      query_text: { enumerable: true, value: "query" },
      account_timezone: { enumerable: true, value: "UTC" },
    });
    await expect(runtime.stageInput({} as never, body as never)).rejects.toThrow("invalid_input");
    await expect(runtime.stageInput({} as never, {
      input_ref: "bad", query_text: " query ", account_timezone: "Not/A_Real_Zone",
    })).rejects.toThrow("invalid_input");
    expect(getterCalls).toBe(0);
  });
});
