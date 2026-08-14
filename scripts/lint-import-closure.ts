/**
 * RULE 18 — import-closure fence.
 *
 * Production entrypoints must not value-import QA, SQLite, GLM, the local
 * test gateway, harness, or spikes. The tracer is `scripts/trace-value-imports.ts`.
 * List changes are David-only: if an entrypoint fails, fix the leak, never
 * this list.
 */
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const ROOT = resolve(import.meta.dir, "..");

const ENTRIES = [
  "drivers/postgres/firebase-authorized-memory-service-process.ts",
  "drivers/postgres/firebase-authorized-memory-service-app.ts",
  "apps/mcp/bun-http.ts",
] as const;

const FORBIDDEN = [
  "apps/qa",
  "drivers/sqlite",
  "drivers/model/glm",
  "integration/local-test-gateway",
  "harness/",
  "spikes/",
] as const;

const args = [
  "run",
  "scripts/trace-value-imports.ts",
  ...ENTRIES,
  ...FORBIDDEN.flatMap((needle) => ["--forbid", needle]),
];

const result = spawnSync("bun", args, { cwd: ROOT, stdio: "inherit" });
process.exit(result.status === null ? 1 : result.status);
