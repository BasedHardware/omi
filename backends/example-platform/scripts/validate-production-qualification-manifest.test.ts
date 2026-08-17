import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  currentProductionMigrationManifestDigest,
  PRODUCTION_QUALIFICATION_BUN_IMAGE,
  PRODUCTION_QUALIFICATION_DEPENDENCY_ARTIFACT_VERSION,
  PRODUCTION_QUALIFICATION_MANIFEST_VERSION,
  PRODUCTION_QUALIFICATION_NODE_CONTROL_IMAGE,
  PRODUCTION_QUALIFICATION_PLATFORM,
  PRODUCTION_QUALIFICATION_POSTGRES_CLIENT,
  PRODUCTION_QUALIFICATION_POSTGRES_SERVER_VERSION,
} from "./production-qualification-manifest";

const roots: string[] = [];
afterEach(() => {
  while (roots.length > 0) rmSync(roots.pop()!, { recursive: true, force: true });
});

const fixture = () => ({
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
  model_resources: [{ resource_digest: "1".repeat(64), max_concurrency: 1 }],
});

const run = (args: readonly string[]) => Bun.spawnSync([
  "bun", "run", "scripts/validate-production-qualification-manifest.ts", ...args,
], { cwd: process.cwd(), stdout: "pipe", stderr: "pipe" });

describe("production qualification manifest CLI", () => {
  test("prints only the stable validation receipt", () => {
    const root = mkdtempSync(join(tmpdir(), "omi-production-qualification-"));
    roots.push(root);
    const input = join(root, "input.json");
    writeFileSync(input, `${JSON.stringify(fixture())}\n`);
    const result = run(["--input", input]);
    expect(result.exitCode).toBe(0);
    const output = JSON.parse(new TextDecoder().decode(result.stdout));
    expect(output).toEqual({
      status: "valid",
      version: PRODUCTION_QUALIFICATION_MANIFEST_VERSION,
      manifest_digest: expect.stringMatching(/^[0-9a-f]{64}$/),
    });
    expect(new TextDecoder().decode(result.stderr)).toBe("");
    expect(JSON.stringify(output)).not.toContain(input);
  });

  test("uses closed errors and never echoes invalid bytes or paths", () => {
    const root = mkdtempSync(join(tmpdir(), "omi-production-qualification-"));
    roots.push(root);
    const input = join(root, "private-name.json");
    writeFileSync(input, '{"secret":"sentinel-private-value"}\n');
    const invalid = run(["--input", input]);
    expect(invalid.exitCode).toBe(1);
    const error = new TextDecoder().decode(invalid.stderr);
    expect(JSON.parse(error)).toEqual({
      status: "error", code: "production_qualification_manifest_invalid",
    });
    expect(error).not.toContain("sentinel-private-value");
    expect(error).not.toContain(input);
    const usage = run([]);
    expect(usage.exitCode).toBe(1);
    expect(JSON.parse(new TextDecoder().decode(usage.stderr))).toEqual({
      status: "error", code: "production_qualification_usage_invalid",
    });
  });
});
