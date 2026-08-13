import { normalizePlainJson, deepFreezePlainJson } from "../core/retrieve/plain-json";
import { sha256CanonicalContent } from "../core/retrieve/content-digest";
import { POSTGRES_MIGRATIONS } from "../drivers/postgres/migrations/manifest";
import {
  POSTGRES_TEST_BUN_IMAGE,
  POSTGRES_TEST_NODE_IMAGE,
} from "./postgres-test-lifecycle";

export const PRODUCTION_QUALIFICATION_MANIFEST_VERSION =
  "production-qualification-manifest-v1" as const;
export const PRODUCTION_QUALIFICATION_PLATFORM = "linux/amd64" as const;
export const PRODUCTION_QUALIFICATION_POSTGRES_SERVER_VERSION = 180004 as const;
export const PRODUCTION_QUALIFICATION_POSTGRES_CLIENT = "postgres@3.4.9" as const;
export const PRODUCTION_QUALIFICATION_DEPENDENCY_ARTIFACT_VERSION =
  "production-dependency-artifact-v1" as const;
export const PRODUCTION_QUALIFICATION_BUN_IMAGE = POSTGRES_TEST_BUN_IMAGE;
export const PRODUCTION_QUALIFICATION_NODE_CONTROL_IMAGE = POSTGRES_TEST_NODE_IMAGE;

const commitPattern = /^[0-9a-f]{40}$/;
const digestPattern = /^[0-9a-f]{64}$/;

export interface ProductionQualificationManifest {
  readonly version: typeof PRODUCTION_QUALIFICATION_MANIFEST_VERSION;
  readonly source: Readonly<{
    source_commit: string;
    dependency_artifact_version: typeof PRODUCTION_QUALIFICATION_DEPENDENCY_ARTIFACT_VERSION;
    dependency_artifact_receipt_digest: string;
    platform: typeof PRODUCTION_QUALIFICATION_PLATFORM;
    bun_image: typeof PRODUCTION_QUALIFICATION_BUN_IMAGE;
    node_control_image: typeof PRODUCTION_QUALIFICATION_NODE_CONTROL_IMAGE;
    postgres_server_version_num: typeof PRODUCTION_QUALIFICATION_POSTGRES_SERVER_VERSION;
    postgres_client: typeof PRODUCTION_QUALIFICATION_POSTGRES_CLIENT;
    migration_manifest_digest: string;
  }>;
  readonly workload: Readonly<{
    account_count: number;
    duration_seconds: number;
    memory_read_steady_rps: number;
    memory_read_burst_rps: number;
    memory_read_steady_concurrency: number;
    memory_read_burst_concurrency: number;
    mcp_steady_rps: number;
    mcp_burst_rps: number;
    mcp_steady_concurrency: number;
    mcp_burst_concurrency: number;
    shadow_jobs_per_minute: number;
  }>;
  readonly objectives: Readonly<{
    p95_memory_read_ms: number;
    p95_mcp_ms: number;
    p95_pool_acquire_ms: number;
    cold_start_ms: number;
    cpu_millicores: number;
    rss_mib: number;
    graceful_shutdown_ms: number;
  }>;
  readonly connections: Readonly<{
    cloud_sql_total: number;
    serving: number;
    candidate: number;
    rollback: number;
    jobs: number;
    migration: number;
    operator: number;
    emergency: number;
  }>;
  readonly recovery: Readonly<{
    authoritative_rpo_seconds: number;
    authoritative_rto_seconds: number;
    rebuildable_rpo_seconds: number;
    rebuildable_rto_seconds: number;
  }>;
  readonly model_resources: readonly Readonly<{
    resource_digest: string;
    max_concurrency: 1;
  }>[];
}

export interface ProductionQualificationManifestReceipt {
  readonly version: "production-qualification-manifest-receipt-v1";
  readonly manifest: ProductionQualificationManifest;
  readonly manifest_digest: string;
  readonly allocated_connections: number;
  readonly unallocated_connections: number;
}

const MINTED_MANIFEST_RECEIPTS = new WeakSet<object>();

const fail = (code = "production_qualification_manifest_invalid"): never => {
  throw new TypeError(code);
};

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail();
  const record = value as Record<string, unknown>;
  const actual = Object.keys(record).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) fail();
  return record;
};

const integer = (value: unknown, minimum: number, maximum: number): number => {
  if (!Number.isSafeInteger(value) || (value as number) < minimum || (value as number) > maximum) fail();
  return value as number;
};

const exactString = <Value extends string>(value: unknown, expected: Value): Value => {
  if (value !== expected) fail();
  return expected;
};

export const currentProductionMigrationManifestDigest = (): string =>
  sha256CanonicalContent(POSTGRES_MIGRATIONS.map((migration) => ({
    version: migration.version,
    name: migration.name,
    sha256: migration.sha256,
  })));

const parseSource = (value: unknown): ProductionQualificationManifest["source"] => {
  const source = exactRecord(value, [
    "bun_image", "dependency_artifact_receipt_digest", "dependency_artifact_version",
    "migration_manifest_digest",
    "node_control_image", "platform", "postgres_client", "postgres_server_version_num",
    "source_commit",
  ]);
  if (typeof source.source_commit !== "string" || !commitPattern.test(source.source_commit)) fail();
  const sourceCommit = source.source_commit as string;
  if (typeof source.dependency_artifact_receipt_digest !== "string"
    || !digestPattern.test(source.dependency_artifact_receipt_digest)) fail();
  if (source.migration_manifest_digest !== currentProductionMigrationManifestDigest()) {
    fail("production_qualification_migration_manifest_mismatch");
  }
  return Object.freeze({
    source_commit: sourceCommit,
    dependency_artifact_version: exactString(
      source.dependency_artifact_version,
      PRODUCTION_QUALIFICATION_DEPENDENCY_ARTIFACT_VERSION,
    ),
    dependency_artifact_receipt_digest: source.dependency_artifact_receipt_digest as string,
    platform: exactString(source.platform, PRODUCTION_QUALIFICATION_PLATFORM),
    bun_image: exactString(source.bun_image, PRODUCTION_QUALIFICATION_BUN_IMAGE),
    node_control_image: exactString(
      source.node_control_image,
      PRODUCTION_QUALIFICATION_NODE_CONTROL_IMAGE,
    ),
    postgres_server_version_num: integer(
      source.postgres_server_version_num,
      PRODUCTION_QUALIFICATION_POSTGRES_SERVER_VERSION,
      PRODUCTION_QUALIFICATION_POSTGRES_SERVER_VERSION,
    ) as typeof PRODUCTION_QUALIFICATION_POSTGRES_SERVER_VERSION,
    postgres_client: exactString(source.postgres_client, PRODUCTION_QUALIFICATION_POSTGRES_CLIENT),
    migration_manifest_digest: source.migration_manifest_digest as string,
  });
};

const parseWorkload = (value: unknown): ProductionQualificationManifest["workload"] => {
  const workload = exactRecord(value, [
    "account_count", "duration_seconds", "mcp_burst_concurrency", "mcp_burst_rps",
    "mcp_steady_concurrency", "mcp_steady_rps", "memory_read_burst_concurrency",
    "memory_read_burst_rps", "memory_read_steady_concurrency", "memory_read_steady_rps",
    "shadow_jobs_per_minute",
  ]);
  const result = {
    account_count: integer(workload.account_count, 2, 1_000_000),
    duration_seconds: integer(workload.duration_seconds, 60, 604_800),
    memory_read_steady_rps: integer(workload.memory_read_steady_rps, 1, 1_000_000),
    memory_read_burst_rps: integer(workload.memory_read_burst_rps, 1, 1_000_000),
    memory_read_steady_concurrency: integer(workload.memory_read_steady_concurrency, 1, 1_000_000),
    memory_read_burst_concurrency: integer(workload.memory_read_burst_concurrency, 1, 1_000_000),
    mcp_steady_rps: integer(workload.mcp_steady_rps, 0, 1_000_000),
    mcp_burst_rps: integer(workload.mcp_burst_rps, 0, 1_000_000),
    mcp_steady_concurrency: integer(workload.mcp_steady_concurrency, 0, 1_000_000),
    mcp_burst_concurrency: integer(workload.mcp_burst_concurrency, 0, 1_000_000),
    shadow_jobs_per_minute: integer(workload.shadow_jobs_per_minute, 1, 1_000_000),
  };
  if (result.memory_read_burst_rps < result.memory_read_steady_rps
    || result.memory_read_burst_concurrency < result.memory_read_steady_concurrency
    || result.mcp_burst_rps < result.mcp_steady_rps
    || result.mcp_burst_concurrency < result.mcp_steady_concurrency
    || ((result.mcp_burst_rps === 0) !== (result.mcp_burst_concurrency === 0))
    || ((result.mcp_steady_rps === 0) !== (result.mcp_steady_concurrency === 0))) fail();
  return Object.freeze(result);
};

const parseObjectives = (value: unknown): ProductionQualificationManifest["objectives"] => {
  const objectives = exactRecord(value, [
    "cold_start_ms", "cpu_millicores", "graceful_shutdown_ms", "p95_mcp_ms",
    "p95_memory_read_ms", "p95_pool_acquire_ms", "rss_mib",
  ]);
  return Object.freeze({
    p95_memory_read_ms: integer(objectives.p95_memory_read_ms, 1, 3_600_000),
    p95_mcp_ms: integer(objectives.p95_mcp_ms, 1, 3_600_000),
    p95_pool_acquire_ms: integer(objectives.p95_pool_acquire_ms, 1, 3_600_000),
    cold_start_ms: integer(objectives.cold_start_ms, 1, 3_600_000),
    cpu_millicores: integer(objectives.cpu_millicores, 1, 1_000_000),
    rss_mib: integer(objectives.rss_mib, 1, 1_048_576),
    graceful_shutdown_ms: integer(objectives.graceful_shutdown_ms, 1, 3_600_000),
  });
};

const parseConnections = (value: unknown): Readonly<{
  connections: ProductionQualificationManifest["connections"];
  allocated: number;
}> => {
  const connections = exactRecord(value, [
    "candidate", "cloud_sql_total", "emergency", "jobs", "migration", "operator",
    "rollback", "serving",
  ]);
  const parsed = Object.freeze({
    cloud_sql_total: integer(connections.cloud_sql_total, 1, 1_000_000),
    serving: integer(connections.serving, 1, 1_000_000),
    candidate: integer(connections.candidate, 1, 1_000_000),
    rollback: integer(connections.rollback, 1, 1_000_000),
    jobs: integer(connections.jobs, 1, 1_000_000),
    migration: integer(connections.migration, 1, 1_000_000),
    operator: integer(connections.operator, 1, 1_000_000),
    emergency: integer(connections.emergency, 1, 1_000_000),
  });
  const allocated = parsed.serving + parsed.candidate + parsed.rollback + parsed.jobs
    + parsed.migration + parsed.operator + parsed.emergency;
  if (!Number.isSafeInteger(allocated) || allocated > parsed.cloud_sql_total) {
    fail("production_qualification_connection_budget_exceeded");
  }
  return Object.freeze({ connections: parsed, allocated });
};

const parseRecovery = (value: unknown): ProductionQualificationManifest["recovery"] => {
  const recovery = exactRecord(value, [
    "authoritative_rpo_seconds", "authoritative_rto_seconds",
    "rebuildable_rpo_seconds", "rebuildable_rto_seconds",
  ]);
  return Object.freeze({
    authoritative_rpo_seconds: integer(recovery.authoritative_rpo_seconds, 0, 31_536_000),
    authoritative_rto_seconds: integer(recovery.authoritative_rto_seconds, 1, 31_536_000),
    rebuildable_rpo_seconds: integer(recovery.rebuildable_rpo_seconds, 0, 31_536_000),
    rebuildable_rto_seconds: integer(recovery.rebuildable_rto_seconds, 1, 31_536_000),
  });
};

const parseModelResources = (
  value: unknown,
): ProductionQualificationManifest["model_resources"] => {
  if (!Array.isArray(value) || value.length < 1 || value.length > 1_024) fail();
  const resources = value as unknown[];
  const output = resources.map((item: unknown) => {
    const resource = exactRecord(item, ["max_concurrency", "resource_digest"]);
    if (typeof resource.resource_digest !== "string" || !digestPattern.test(resource.resource_digest)) fail();
    const resourceDigest = resource.resource_digest as string;
    return Object.freeze({
      resource_digest: resourceDigest,
      max_concurrency: integer(resource.max_concurrency, 1, 1) as 1,
    });
  });
  if (output.some((item, index: number) => index > 0
    && output[index - 1]!.resource_digest >= item.resource_digest)) fail();
  return Object.freeze(output);
};

export const parseProductionQualificationManifest = (
  input: unknown,
): Readonly<ProductionQualificationManifestReceipt> => {
  let normalized: unknown;
  try {
    normalized = normalizePlainJson(input);
  } catch {
    return fail();
  }
  const root = exactRecord(normalized, [
    "connections", "model_resources", "objectives", "recovery", "source", "version", "workload",
  ]);
  const version = exactString(root.version, PRODUCTION_QUALIFICATION_MANIFEST_VERSION);
  const source = parseSource(root.source);
  const workload = parseWorkload(root.workload);
  const objectives = parseObjectives(root.objectives);
  const connections = parseConnections(root.connections);
  const recovery = parseRecovery(root.recovery);
  const modelResources = parseModelResources(root.model_resources);
  const manifest = deepFreezePlainJson({
    version,
    source,
    workload,
    objectives,
    connections: connections.connections,
    recovery,
    model_resources: modelResources,
  }) as ProductionQualificationManifest;
  const receipt = Object.freeze({
    version: "production-qualification-manifest-receipt-v1" as const,
    manifest,
    manifest_digest: sha256CanonicalContent(manifest),
    allocated_connections: connections.allocated,
    unallocated_connections: connections.connections.cloud_sql_total - connections.allocated,
  });
  MINTED_MANIFEST_RECEIPTS.add(receipt);
  return receipt;
};

/**
 * Proves that the receipt was produced by the strict parser in this process.
 * Structural lookalikes cannot authorize production startup composition.
 */
export const assertProductionQualificationManifestReceipt = (
  value: unknown,
): Readonly<ProductionQualificationManifestReceipt> => {
  if (value === null || typeof value !== "object" || !MINTED_MANIFEST_RECEIPTS.has(value)) {
    return fail("production_qualification_manifest_receipt_invalid");
  }
  return value as Readonly<ProductionQualificationManifestReceipt>;
};
