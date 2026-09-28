import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

import {
  LOCAL_APPLICATION_ID,
  LOCAL_FIREBASE_PROJECT_ID,
  LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
} from "./prod-local";
import {
  PROD_LOCAL_IDENTITY_SEED_GENERATION_UNRELEASED,
  PROD_LOCAL_IDENTITY_SEED_USAGE,
  parseSeedUid,
  prodLocalIdentitySeedCoordinates,
  seedProdLocalFirebaseAuthorizationSql,
  validFirebaseUid,
} from "./prod-local-identity-seed";

const platformRoot = new URL("..", import.meta.url).pathname;

const FORBIDDEN = [
  "apps/qa",
  "drivers/sqlite",
  "drivers/model/glm",
  "integration/local-test-gateway",
  "harness/",
  "spikes/",
] as const;

test("prod-local-identity-seed parses a single uid and rejects extras", () => {
  expect(parseSeedUid(["--uid", "firebase-user-1"])).toBe("firebase-user-1");
  expect(parseSeedUid([])).toBeNull();
  expect(parseSeedUid(["--uid"])).toBeNull();
  expect(parseSeedUid(["--uid", "--uid"])).toBeNull();
  expect(parseSeedUid(["--uid", "firebase-user-1", "--force"])).toBeNull();
  expect(validFirebaseUid("firebase-user-1")).toBe(true);
  expect(validFirebaseUid("")).toBe(false);
  expect(validFirebaseUid("bad uid")).toBe(false);
});

test("prod-local-identity-seed uses the test revision and head SQL surfaces", () => {
  const coordinates = prodLocalIdentitySeedCoordinates("emulator-uid-fixture");
  expect(coordinates.firebase_project_id).toBe(LOCAL_FIREBASE_PROJECT_ID);
  expect(coordinates.application_id).toBe(LOCAL_APPLICATION_ID);
  expect(coordinates.account_id).toBe("account:prod-local-identity:emulator-uid-fixture");
  const statements = seedProdLocalFirebaseAuthorizationSql(coordinates, 1_700_000_000);
  const text = statements.map((statement) => statement.text).join("\n");
  expect(text).toContain("INSERT INTO omi_memory.platform_accounts");
  expect(text).toContain("INSERT INTO omi_memory.account_control_revisions");
  expect(text).toContain("INSERT INTO omi_memory.account_control_heads");
  expect(text).toContain("INSERT INTO omi_memory.application_credential_revisions");
  expect(text).toContain("INSERT INTO omi_memory.application_credential_heads");
  expect(text).toContain("INSERT INTO omi_memory.application_grant_revisions");
  expect(text).toContain("INSERT INTO omi_memory.application_grant_heads");
  expect(text).toContain("INSERT INTO omi_memory.firebase_identity_bindings");
  expect(text).toContain("INSERT INTO omi_memory.firebase_application_credential_bindings");
  expect(text).toContain("'firebase'");
  expect(text).toContain("'firebase-id-token'");
  expect(text).toContain("'memories.read'");
  expect(text).not.toContain("postgres_restore_admission");
  expect(text).not.toContain("INSERT INTO omi_memory.lookup");
  expect(LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST).toMatch(/^[a-f0-9]{64}$/);
  const source = readFileSync(new URL("./prod-local-identity-seed.ts", import.meta.url), "utf8");
  expect(source).toContain(PROD_LOCAL_IDENTITY_SEED_GENERATION_UNRELEASED);
  expect(source).toContain("will not insert a fake restore-admission digest");
});

test("prod-local-identity-seed refuses without a uid", () => {
  const result = spawnSync("bun", ["run", "scripts/prod-local-identity-seed.ts"], {
    cwd: platformRoot,
    encoding: "utf8",
  });
  expect(result.status).toBe(1);
  expect(`${result.stdout}${result.stderr}`).toContain(PROD_LOCAL_IDENTITY_SEED_USAGE);
});

test("prod-local-identity-seed value-import closure stays outside the rule-18 forbidden set", () => {
  const result = spawnSync("bun", [
    "run",
    "scripts/trace-value-imports.ts",
    "scripts/prod-local-identity-seed.ts",
    ...FORBIDDEN.flatMap((needle) => ["--forbid", needle]),
  ], {
    cwd: platformRoot,
    encoding: "utf8",
  });
  expect(result.status).toBe(0);
  expect(`${result.stdout}${result.stderr}`).not.toContain("FORBIDDEN");
});
