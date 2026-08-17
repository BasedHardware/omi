import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

import {
  FIREBASE_AUTH_EMULATOR_HOST_ENV,
  LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
  PROD_LOCAL_AMBIENT_SELECTOR,
  PROD_LOCAL_EMULATOR_FORBIDDEN,
  PROD_LOCAL_IDENTITY_CANNOT_MINT,
  PROD_LOCAL_IDENTITY_EMULATOR_NOT_PRODUCTION,
  PROD_LOCAL_IDENTITY_ENV,
  PROD_LOCAL_IDENTITY_ENV_VALUE,
  PROD_LOCAL_IDENTITY_FLAG,
  PROD_LOCAL_LOCAL_IDENTITY_ENV_INVALID,
  PROD_LOCAL_LOCAL_IDENTITY_REQUIRES_EMULATOR,
  PROD_LOCAL_PG_ABSENT,
  PROD_LOCAL_PG_NOT_RUNNING,
  interpretManagedPostgresState,
  resolveProdLocalIdentity,
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
  expect(PROD_LOCAL_EMULATOR_FORBIDDEN).toBe(
    "omi prod-local: deployed Firebase identity forbids the Auth emulator.",
  );
  expect(PROD_LOCAL_IDENTITY_EMULATOR_NOT_PRODUCTION).toBe(
    "omi prod-local: emulator identity — not production.",
  );
  expect(PROD_LOCAL_IDENTITY_EMULATOR_NOT_PRODUCTION).not.toBe(PROD_LOCAL_IDENTITY_CANNOT_MINT);
  expect(LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST).toMatch(/^[a-f0-9]{64}$/);
  expect(source).toContain("createPostgresFirebaseAuthorizedMemoryServiceProcess");
  expect(source).toContain("What this script will not do");
  expect(source).toContain(PROD_LOCAL_IDENTITY_CANNOT_MINT);
  expect(source).toContain(PROD_LOCAL_IDENTITY_EMULATOR_NOT_PRODUCTION);
  expect(source).toContain("runtime_mode: identity.runtime_mode");
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

const argv = (...flags: string[]): string[] => ["bun", "scripts/prod-local.ts", ...flags];

test("default prod-local identity stays deployed and still forbids the emulator", () => {
  expect(resolveProdLocalIdentity(argv(), {})).toEqual({
    kind: "deployed",
    runtime_mode: "deployed",
  });
  expect(resolveProdLocalIdentity(argv(), { [FIREBASE_AUTH_EMULATOR_HOST_ENV]: "127.0.0.1:19099" }))
    .toMatchObject({ kind: "refuse" });
  expect(resolveProdLocalIdentity(argv(), { [FIREBASE_AUTH_EMULATOR_HOST_ENV]: "" }))
    .toMatchObject({ kind: "refuse" });
  const presentEmpty = resolveProdLocalIdentity(argv(), { [FIREBASE_AUTH_EMULATOR_HOST_ENV]: "" });
  if (presentEmpty.kind !== "refuse") throw new Error("expected refuse");
  expect(presentEmpty.message).toContain(PROD_LOCAL_EMULATOR_FORBIDDEN);
  expect(presentEmpty.message).toContain("runtime_mode=deployed");
  const presentHost = resolveProdLocalIdentity(
    argv(),
    { [FIREBASE_AUTH_EMULATOR_HOST_ENV]: "127.0.0.1:19099" },
  );
  if (presentHost.kind !== "refuse") throw new Error("expected refuse");
  expect(presentHost.message.startsWith(PROD_LOCAL_EMULATOR_FORBIDDEN)).toBe(true);
});

test("local-identity opt-in requires the emulator and never takes the deployed refusal", () => {
  const flagWithoutHost = resolveProdLocalIdentity(argv(PROD_LOCAL_IDENTITY_FLAG), {});
  expect(flagWithoutHost.kind).toBe("refuse");
  if (flagWithoutHost.kind !== "refuse") throw new Error("expected refuse");
  expect(flagWithoutHost.message).toContain(PROD_LOCAL_LOCAL_IDENTITY_REQUIRES_EMULATOR);
  expect(flagWithoutHost.message).not.toContain(PROD_LOCAL_EMULATOR_FORBIDDEN);

  const emptyHost = resolveProdLocalIdentity(argv(PROD_LOCAL_IDENTITY_FLAG), {
    [FIREBASE_AUTH_EMULATOR_HOST_ENV]: "",
  });
  expect(emptyHost.kind).toBe("refuse");
  if (emptyHost.kind !== "refuse") throw new Error("expected refuse");
  expect(emptyHost.message).toContain(PROD_LOCAL_LOCAL_IDENTITY_REQUIRES_EMULATOR);

  const envWithoutHost = resolveProdLocalIdentity(argv(), {
    [PROD_LOCAL_IDENTITY_ENV]: PROD_LOCAL_IDENTITY_ENV_VALUE,
  });
  expect(envWithoutHost.kind).toBe("refuse");
  if (envWithoutHost.kind !== "refuse") throw new Error("expected refuse");
  expect(envWithoutHost.message).toContain(PROD_LOCAL_LOCAL_IDENTITY_REQUIRES_EMULATOR);

  expect(resolveProdLocalIdentity(argv(PROD_LOCAL_IDENTITY_FLAG), {
    [FIREBASE_AUTH_EMULATOR_HOST_ENV]: "127.0.0.1:19099",
  })).toEqual({ kind: "local_test", runtime_mode: "local_test" });
  expect(resolveProdLocalIdentity(argv(), {
    [PROD_LOCAL_IDENTITY_ENV]: PROD_LOCAL_IDENTITY_ENV_VALUE,
    [FIREBASE_AUTH_EMULATOR_HOST_ENV]: "127.0.0.1:19099",
  })).toEqual({ kind: "local_test", runtime_mode: "local_test" });
});

test("unknown OMI_PROD_LOCAL_IDENTITY values refuse instead of opting in", () => {
  const decided = resolveProdLocalIdentity(argv(), { [PROD_LOCAL_IDENTITY_ENV]: "production" });
  expect(decided.kind).toBe("refuse");
  if (decided.kind !== "refuse") throw new Error("expected refuse");
  expect(decided.message).toContain(PROD_LOCAL_LOCAL_IDENTITY_ENV_INVALID);
  expect(decided.message).not.toContain(PROD_LOCAL_EMULATOR_FORBIDDEN);
});
