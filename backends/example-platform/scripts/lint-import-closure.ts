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
 * cannot share the cloud list. What it must never link is the
 * Codex-subscription transport, the GLM client, or anything under
 * `harness/` (research code carrying a third provider profile of its own),
 * `spikes/`, or `migration/`.
 *
 * This is a dependency/import-closure fence. The tracer
 * (`scripts/trace-value-imports.ts`) walks the transitive value-import
 * closure of the listed TypeScript entrypoints. Type-only imports are
 * excluded because they erase at runtime. `--forbid` is a path-substring
 * match against that closure. That is load-bearing: a production image
 * cannot link `drivers/model/glm`, `drivers/model/codex` (LOCAL),
 * `harness/`, `spikes/`, or `migration/` and still pass. Two defects of
 * exactly that shape have already shipped past the port-registry and
 * wire-path fences — a model fake via `apps/qa`, and the GLM client via
 * predicate-batch — and this fence is the ratchet that made them
 * unshippable.
 *
 * It does not observe network traffic. It does not inspect `fetch` URLs,
 * environment values, or which host a running process contacted. An inline
 * `fetch` to an unsanctioned host from a module already on the closure
 * does not fail this fence. The plan for a host-level follow-up is
 * `docs/network-fence-proposal.md`.
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
