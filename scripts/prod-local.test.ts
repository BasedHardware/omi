import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

import {
  LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
  PROD_LOCAL_AMBIENT_SELECTOR,
  PROD_LOCAL_IDENTITY_CANNOT_MINT,
  PROD_LOCAL_PG_ABSENT,
  PROD_LOCAL_PG_NOT_RUNNING,
  interpretManagedPostgresState,
} from "./prod-local";
import { createPostgresTestState, withPostgresTestPort } from "./postgres-test-lifecycle";

const platformRoot = new URL("..", import.meta.url).pathname;

const FORBIDDEN = [
  "apps/qa",
  "drivers/sqlite",
  "drivers/model/glm",
  "integration/local-test-gateway",
  "harness/",
  "spikes/",
] as const;

test("managed PostgreSQL presence is fail-closed without fabricating a runtime", () => {
  expect(interpretManagedPostgresState(null)).toEqual({ kind: "absent" });
  const created = createPostgresTestState(platformRoot, () => Uint8Array.from({ length: 12 }, () => 0xcd));
  expect(interpretManagedPostgresState(created)).toEqual({ kind: "not_ready" });
  const ready = withPostgresTestPort(created, 15_432);
  expect(interpretManagedPostgresState(ready)).toEqual({
    kind: "configured",
    state: ready,
    hostPort: 15_432,
  });
});

test("prod-local documents the exact refusal and identity-cannot-mint messages", () => {
  const source = readFileSync(new URL("./prod-local.ts", import.meta.url), "utf8");
  expect(PROD_LOCAL_PG_ABSENT).toBe("omi prod-local: local PostgreSQL runtime is absent.");
  expect(PROD_LOCAL_PG_NOT_RUNNING).toBe(
    "omi prod-local: local PostgreSQL is configured but not accepting connections.",
  );
  expect(PROD_LOCAL_AMBIENT_SELECTOR).toBe(
    "omi prod-local: ambient DATABASE_URL / PG* selectors are forbidden.",
  );
  expect(PROD_LOCAL_IDENTITY_CANNOT_MINT).toBe(
    "omi prod-local: Firebase identity cannot be minted locally.",
  );
  expect(LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST).toMatch(/^[a-f0-9]{64}$/);
  expect(source).toContain("createPostgresFirebaseAuthorizedMemoryServiceProcess");
  expect(source).toContain("What this script will not do");
  expect(source).not.toMatch(/from\s+["'][^"']*apps\/qa/);
  expect(source).not.toMatch(/from\s+["'][^"']*drivers\/sqlite/);
  expect(source).not.toMatch(/from\s+["'][^"']*dev-server/);
});

test("prod-local value-import closure stays outside the rule-18 forbidden set", () => {
  const result = spawnSync("bun", [
    "run",
    "scripts/trace-value-imports.ts",
    "scripts/prod-local.ts",
    ...FORBIDDEN.flatMap((needle) => ["--forbid", needle]),
  ], {
    cwd: platformRoot,
    encoding: "utf8",
  });
  expect(result.status).toBe(0);
  expect(`${result.stdout}${result.stderr}`).not.toContain("FORBIDDEN");
});
