import { expect, test } from "bun:test";

import { MODEL_PIPELINE_RESOURCE_VERSION } from "../../apps/service/workers/model-pipeline-exclusivity";
import type { PostgresSessionAdvisoryLockPool } from "./connection";
import { createPostgresModelPipelineExclusivity } from "./model-pipeline-exclusivity";

test("PostgreSQL model exclusivity derives a stable signed advisory coordinate", async () => {
  const seen: (readonly [number, number])[] = [];
  const pool: PostgresSessionAdvisoryLockPool = {
    async tryWithSessionAdvisoryLock(key, callback) {
      seen.push(key);
      return Object.freeze({ acquired: true as const, value: await callback(new AbortController().signal) });
    },
  };
  const port = createPostgresModelPipelineExclusivity(pool);
  await expect(port.runExclusive({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: "ffffffff80000000" + "0".repeat(48),
  }, async () => 7)).resolves.toEqual({ kind: "completed", value: 7 });
  expect(seen).toEqual([[-1, -2147483648]]);
});

test("PostgreSQL model exclusivity closes contention and infrastructure failure", async () => {
  const busy = createPostgresModelPipelineExclusivity({
    tryWithSessionAdvisoryLock: async () => Object.freeze({ acquired: false as const }),
  });
  await expect(busy.runExclusive({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: "1".repeat(64),
  }, async () => "never")).resolves.toEqual({ kind: "busy" });
  const failed = createPostgresModelPipelineExclusivity({
    tryWithSessionAdvisoryLock: async () => { throw new Error("provider text"); },
  });
  await expect(failed.runExclusive({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: "2".repeat(64),
  }, async () => "never")).resolves.toEqual({ kind: "unavailable" });
});
