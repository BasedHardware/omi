import { describe, expect, test } from "bun:test";

import type { PostgresTransactionPool } from "./connection";
import { createPostgresListenAttributionBeliefOneShotRuntime } from
  "./listen-attribution-belief-one-shot-runtime";

const unusedPool = (): PostgresTransactionPool => Object.freeze({
  withTransaction: async () => { throw new Error("postgres_must_not_open"); },
});

describe("PostgreSQL Listen attribution belief one-shot runtime", () => {
  test("constructs inertly and exposes only explicit bounded execution", () => {
    let resolverCalls = 0;
    const runtime = createPostgresListenAttributionBeliefOneShotRuntime({
      pool: unusedPool(),
      resolve_calibrator: async () => {
        resolverCalls += 1;
        throw new Error("calibrator_must_not_resolve_at_construction");
      },
    });
    expect(Object.keys(runtime)).toEqual(["run"]);
    expect(typeof runtime.run).toBe("function");
    expect(resolverCalls).toBe(0);
  });

  test("rejects hostile options without invoking accessors", () => {
    let getterCalls = 0;
    const hostile = Object.defineProperties({}, {
      pool: { enumerable: true, value: unusedPool() },
      resolve_calibrator: {
        enumerable: true,
        get() { getterCalls += 1; return async () => null; },
      },
    });
    expect(() => createPostgresListenAttributionBeliefOneShotRuntime(hostile as never))
      .toThrow("invalid_options");
    expect(getterCalls).toBe(0);
  });

  test("rejects hostile or unbounded requests before PostgreSQL", async () => {
    let getterCalls = 0;
    const runtime = createPostgresListenAttributionBeliefOneShotRuntime({
      pool: unusedPool(), resolve_calibrator: async () => null,
    });
    const hostile = Object.defineProperties({}, {
      input_ref: { enumerable: true, get() { getterCalls += 1; return "hidden"; } },
      input_frontier: { enumerable: true, value: "a".repeat(64) },
      assignment_bundle: { enumerable: true, value: {} },
      evaluation_run_id: { enumerable: true, value: `mer1_${"b".repeat(64)}` },
      repeats: { enumerable: true, value: 1 },
    });
    await expect(runtime.run({} as never, hostile as never)).rejects.toThrow("invalid_request");
    await expect(runtime.run({} as never, {
      input_ref: `labinput1_${"c".repeat(64)}`,
      input_frontier: "d".repeat(64), assignment_bundle: {} as never,
      evaluation_run_id: `mer1_${"e".repeat(64)}`, repeats: 21,
    })).rejects.toThrow("invalid_request");
    expect(getterCalls).toBe(0);
  });
});
