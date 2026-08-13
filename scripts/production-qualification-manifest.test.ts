import { describe, expect, test } from "bun:test";

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
} from "./production-qualification-manifest";

const manifest = () => ({
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
    account_count: 100,
    duration_seconds: 3_600,
    memory_read_steady_rps: 5,
    memory_read_burst_rps: 20,
    memory_read_steady_concurrency: 5,
    memory_read_burst_concurrency: 20,
    mcp_steady_rps: 0,
    mcp_burst_rps: 0,
    mcp_steady_concurrency: 0,
    mcp_burst_concurrency: 0,
    shadow_jobs_per_minute: 2,
  },
  objectives: {
    p95_memory_read_ms: 750,
    p95_mcp_ms: 1_000,
    p95_pool_acquire_ms: 100,
    cold_start_ms: 10_000,
    cpu_millicores: 2_000,
    rss_mib: 1_536,
    graceful_shutdown_ms: 30_000,
  },
  connections: {
    cloud_sql_total: 100,
    serving: 30,
    candidate: 10,
    rollback: 10,
    jobs: 20,
    migration: 5,
    operator: 5,
    emergency: 10,
  },
  recovery: {
    authoritative_rpo_seconds: 0,
    authoritative_rto_seconds: 3_600,
    rebuildable_rpo_seconds: 900,
    rebuildable_rto_seconds: 14_400,
  },
  model_resources: [
    { resource_digest: "1".repeat(64), max_concurrency: 1 },
    { resource_digest: "2".repeat(64), max_concurrency: 1 },
  ],
});

describe("production qualification manifest", () => {
  test("seals every qualification coordinate and accounts for the full connection budget", () => {
    const receipt = parseProductionQualificationManifest(manifest());
    expect(receipt.version).toBe("production-qualification-manifest-receipt-v1");
    expect(receipt.manifest_digest).toMatch(/^[0-9a-f]{64}$/);
    expect(receipt.allocated_connections).toBe(90);
    expect(receipt.unallocated_connections).toBe(10);
    expect(Object.isFrozen(receipt)).toBe(true);
    expect(Object.isFrozen(receipt.manifest)).toBe(true);
    expect(Object.isFrozen(receipt.manifest.model_resources)).toBe(true);
  });

  test("is byte-stable and changes for every material qualification class", () => {
    const base = manifest();
    const digest = parseProductionQualificationManifest(base).manifest_digest;
    expect(parseProductionQualificationManifest(structuredClone(base)).manifest_digest).toBe(digest);
    const changes = [
      { ...base, source: { ...base.source, source_commit: "b".repeat(40) } },
      { ...base, source: { ...base.source, dependency_artifact_receipt_digest: "f".repeat(64) } },
      { ...base, workload: { ...base.workload, account_count: 101 } },
      { ...base, objectives: { ...base.objectives, rss_mib: 1_537 } },
      { ...base, connections: { ...base.connections, serving: 31 } },
      { ...base, recovery: { ...base.recovery, authoritative_rto_seconds: 3_601 } },
      { ...base, model_resources: [{ resource_digest: "3".repeat(64), max_concurrency: 1 }] },
    ];
    for (const changed of changes) {
      expect(parseProductionQualificationManifest(changed).manifest_digest).not.toBe(digest);
    }
  });

  test("refuses missing, extra, malformed, accessor, proxy, and aliased input", () => {
    const base = manifest();
    expect(() => parseProductionQualificationManifest({ ...base, extra: true })).toThrow();
    const { recovery: _omitted, ...missing } = base;
    expect(() => parseProductionQualificationManifest(missing)).toThrow();
    expect(() => parseProductionQualificationManifest({ ...base, version: "v2" })).toThrow();
    expect(() => parseProductionQualificationManifest(new Proxy(base, {}))).toThrow();
    let getterCalls = 0;
    const hostile = Object.defineProperty({ ...base }, "workload", {
      enumerable: true,
      get() { getterCalls += 1; return base.workload; },
    });
    expect(() => parseProductionQualificationManifest(hostile)).toThrow();
    expect(getterCalls).toBe(0);
    const shared = { resource_digest: "1".repeat(64), max_concurrency: 1 };
    expect(() => parseProductionQualificationManifest({
      ...base, model_resources: [shared, shared],
    })).toThrow();
  });

  test("pins source, runtime images, PostgreSQL, and current migration history", () => {
    const base = manifest();
    for (const source of [
      { ...base.source, source_commit: "main" },
      { ...base.source, dependency_artifact_receipt_digest: "artifact.json" },
      { ...base.source, bun_image: "oven/bun:latest" },
      { ...base.source, node_control_image: "node:latest" },
      { ...base.source, platform: "linux/arm64" },
      { ...base.source, postgres_server_version_num: 180005 },
      { ...base.source, postgres_client: "postgres@next" },
      { ...base.source, migration_manifest_digest: "0".repeat(64) },
    ]) expect(() => parseProductionQualificationManifest({ ...base, source })).toThrow();
  });

  test("requires coherent traffic rates and explicit positive shadow work", () => {
    const base = manifest();
    for (const workload of [
      { ...base.workload, memory_read_burst_rps: 4 },
      { ...base.workload, memory_read_burst_concurrency: 4 },
      { ...base.workload, mcp_burst_rps: 1, mcp_burst_concurrency: 0 },
      { ...base.workload, mcp_burst_rps: 0, mcp_burst_concurrency: 1 },
      { ...base.workload, shadow_jobs_per_minute: 0 },
      { ...base.workload, account_count: 1 },
    ]) expect(() => parseProductionQualificationManifest({ ...base, workload })).toThrow();
  });

  test("rejects overcommitted and incomplete connection budgets", () => {
    const base = manifest();
    expect(() => parseProductionQualificationManifest({
      ...base,
      connections: { ...base.connections, serving: 50 },
    })).toThrow("production_qualification_connection_budget_exceeded");
    expect(() => parseProductionQualificationManifest({
      ...base,
      connections: { ...base.connections, emergency: 0 },
    })).toThrow();
  });

  test("requires sorted unique opaque resources and exactly one pipeline", () => {
    const base = manifest();
    for (const model_resources of [
      [],
      [{ resource_digest: "raw-api-key", max_concurrency: 1 }],
      [{ resource_digest: "1".repeat(64), max_concurrency: 2 }],
      [
        { resource_digest: "2".repeat(64), max_concurrency: 1 },
        { resource_digest: "1".repeat(64), max_concurrency: 1 },
      ],
      [
        { resource_digest: "1".repeat(64), max_concurrency: 1 },
        { resource_digest: "1".repeat(64), max_concurrency: 1 },
      ],
    ]) expect(() => parseProductionQualificationManifest({ ...base, model_resources })).toThrow();
  });

  test("does not mutate caller input and rejects unsafe numeric decisions", () => {
    const base = manifest();
    const before = structuredClone(base);
    parseProductionQualificationManifest(base);
    expect(base).toEqual(before);
    expect(() => parseProductionQualificationManifest({
      ...base,
      objectives: { ...base.objectives, rss_mib: Number.MAX_SAFE_INTEGER + 1 },
    })).toThrow();
    expect(() => parseProductionQualificationManifest({
      ...base,
      recovery: { ...base.recovery, authoritative_rpo_seconds: -1 },
    })).toThrow();
  });
});
