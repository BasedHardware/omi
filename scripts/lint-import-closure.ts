/**
 * RULE 18 — import-closure fence.
 *
 * Two groups, because the two deployments have different legitimate contents.
 *
 * CLOUD: the hosted entrypoints must not value-import QA, SQLite, GLM, the
 * local test gateway, harness, spikes, or migration.
 *
 * LOCAL: the entrypoint David actually runs — the local service behind the
 * macOS app. It legitimately links SQLite and the QA persona seeder, so it
 * cannot share the cloud list. What it must never link is a model transport
 * to any provider outside the two sanctioned leaks (Firebase auth and the
 * chat model provider): the Codex-subscription transport, the GLM client, or
 * anything reached through `harness/`, which is research code carrying a
 * third provider profile of its own.
 *
 * The tracer is `scripts/trace-value-imports.ts`. List changes are
 * David-only: if an entrypoint fails, fix the leak, never this list.
 */
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const ROOT = resolve(import.meta.dir, "..");

const CLOUD_ENTRIES = [
  "drivers/postgres/firebase-authorized-memory-service-process.ts",
  "drivers/postgres/firebase-authorized-memory-service-app.ts",
  "apps/mcp/bun-http.ts",
] as const;

const CLOUD_FORBIDDEN = [
  "apps/qa",
  "drivers/sqlite",
  "drivers/model/glm",
  "integration/local-test-gateway",
  "harness/",
  "spikes/",
  "migration/",
] as const;

const LOCAL_ENTRIES = ["apps/service/bin/dev-server.ts"] as const;

const LOCAL_FORBIDDEN = [
  "drivers/model/codex",
  "drivers/model/glm",
  "harness/",
  "spikes/",
  "migration/",
] as const;

const trace = (entries: readonly string[], forbidden: readonly string[]): number => {
  const result = spawnSync(
    "bun",
    [
      "run",
      "scripts/trace-value-imports.ts",
      ...entries,
      ...forbidden.flatMap((needle) => ["--forbid", needle]),
    ],
    { cwd: ROOT, stdio: "inherit" },
  );
  return result.status === null ? 1 : result.status;
};

const cloud = trace(CLOUD_ENTRIES, CLOUD_FORBIDDEN);
const local = trace(LOCAL_ENTRIES, LOCAL_FORBIDDEN);
process.exit(cloud === 0 && local === 0 ? 0 : 1);
