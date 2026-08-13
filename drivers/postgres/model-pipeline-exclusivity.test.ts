import { expect, test } from "bun:test";

import { MODEL_PIPELINE_RESOURCE_VERSION } from "../../apps/service/workers/model-pipeline-exclusivity";
import {
  currentProductionMigrationManifestDigest,
  parseProductionQualificationManifest,
  PRODUCTION_QUALIFICATION_BUN_IMAGE,
  PRODUCTION_QUALIFICATION_DEPENDENCY_ARTIFACT_VERSION,
  PRODUCTION_QUALIFICATION_MANIFEST_VERSION,
  PRODUCTION_QUALIFICATION_NODE_CONTROL_IMAGE,
  PRODUCTION_QUALIFICATION_PLATFORM,
  PRODUCTION_QUALIFICATION_POSTGRES_CLIENT,
  PRODUCTION_QUALIFICATION_POSTGRES_SERVER_VERSION,
} from "../../scripts/production-qualification-manifest";
import type { PostgresSessionAdvisoryLockPool } from "./connection";
import { createPostgresProductionModelPipelineExclusivity } from "./model-pipeline-exclusivity";

const receipt = (...digests: string[]) => parseProductionQualificationManifest({
  version: PRODUCTION_QUALIFICATION_MANIFEST_VERSION,
  source: {
    source_commit: "a".repeat(40),
    dependency_artifact_version: PRODUCTION_QUALIFICATION_DEPENDENCY_ARTIFACT_VERSION,
    dependency_artifact_receipt_digest: "0".repeat(64),
    platform: PRODUCTION_QUALIFICATION_PLATFORM,
    bun_image: PRODUCTION_QUALIFICATION_BUN_IMAGE,
    node_control_image: PRODUCTION_QUALIFICATION_NODE_CONTROL_IMAGE,
    postgres_server_version_num: PRODUCTION_QUALIFICATION_POSTGRES_SERVER_VERSION,
    postgres_client: PRODUCTION_QUALIFICATION_POSTGRES_CLIENT,
    migration_manifest_digest: currentProductionMigrationManifestDigest(),
  },
  workload: {
    account_count: 2, duration_seconds: 60,
    memory_read_steady_rps: 1, memory_read_burst_rps: 1,
    memory_read_steady_concurrency: 1, memory_read_burst_concurrency: 1,
    mcp_steady_rps: 0, mcp_burst_rps: 0,
    mcp_steady_concurrency: 0, mcp_burst_concurrency: 0,
    shadow_jobs_per_minute: 1,
  },
  objectives: {
    p95_memory_read_ms: 1, p95_mcp_ms: 1, p95_pool_acquire_ms: 1,
    cold_start_ms: 1, cpu_millicores: 1, rss_mib: 1, graceful_shutdown_ms: 1,
  },
  connections: {
    cloud_sql_total: 7, serving: 1, candidate: 1, rollback: 1,
    jobs: 1, migration: 1, operator: 1, emergency: 1,
  },
  recovery: {
    authoritative_rpo_seconds: 0, authoritative_rto_seconds: 1,
    rebuildable_rpo_seconds: 0, rebuildable_rto_seconds: 1,
  },
  model_resources: [...digests].sort().map((resource_digest) => ({
    resource_digest, max_concurrency: 1,
  })),
});

test("PostgreSQL model exclusivity derives a stable signed advisory coordinate", async () => {
  const seen: (readonly [number, number])[] = [];
  const pool: PostgresSessionAdvisoryLockPool = {
    async tryWithSessionAdvisoryLock(key, callback) {
      seen.push(key);
      return Object.freeze({ acquired: true as const, value: await callback(new AbortController().signal) });
    },
  };
  const resourceDigest = "ffffffff80000000" + "0".repeat(48);
  const port = createPostgresProductionModelPipelineExclusivity(pool, receipt(resourceDigest));
  await expect(port.runExclusive({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: resourceDigest,
  }, async () => 7)).resolves.toEqual({ kind: "completed", value: 7 });
  expect(seen).toEqual([[-1, -2147483648]]);
});

test("PostgreSQL model exclusivity closes contention and infrastructure failure", async () => {
  const busyResource = "1".repeat(64);
  const busy = createPostgresProductionModelPipelineExclusivity({
    tryWithSessionAdvisoryLock: async () => Object.freeze({ acquired: false as const }),
  }, receipt(busyResource));
  await expect(busy.runExclusive({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: busyResource,
  }, async () => "never")).resolves.toEqual({ kind: "busy" });
  const failedResource = "2".repeat(64);
  const failed = createPostgresProductionModelPipelineExclusivity({
    tryWithSessionAdvisoryLock: async () => { throw new Error("provider text"); },
  }, receipt(failedResource));
  await expect(failed.runExclusive({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: failedResource,
  }, async () => "never")).resolves.toEqual({ kind: "unavailable" });
});

test("PostgreSQL model exclusivity refuses undeclared resources before touching the pool", async () => {
  let poolCalls = 0;
  const port = createPostgresProductionModelPipelineExclusivity({
    tryWithSessionAdvisoryLock: async () => {
      poolCalls += 1;
      throw new Error("must not run");
    },
  }, receipt("a".repeat(64)));
  await expect(port.runExclusive({
    version: MODEL_PIPELINE_RESOURCE_VERSION,
    resource_digest: "b".repeat(64),
  }, async () => "never")).resolves.toEqual({ kind: "unavailable" });
  expect(poolCalls).toBe(0);
});

test("PostgreSQL model exclusivity rejects forged manifest receipts before touching the pool", () => {
  let poolCalls = 0;
  expect(() => createPostgresProductionModelPipelineExclusivity({
    tryWithSessionAdvisoryLock: async () => {
      poolCalls += 1;
      throw new Error("must not run");
    },
  }, structuredClone(receipt("a".repeat(64))))).toThrow(
    "production_qualification_manifest_receipt_invalid",
  );
  expect(poolCalls).toBe(0);
});
