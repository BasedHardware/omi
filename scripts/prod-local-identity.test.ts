import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";

import {
  AUTH_EMULATOR_PORT,
  FIREBASE_AUTH_EMULATOR_HOST_VALUE,
  LOCAL_FIREBASE_PROJECT_ID,
  PROD_LOCAL_IDENTITY_USAGE,
  firebaseEmulatorConfig,
  mintEmulatorIdentity,
  parseIdentityAction,
} from "./prod-local-identity";

const platformRoot = new URL("..", import.meta.url).pathname;

const FORBIDDEN = [
  "apps/qa",
  "drivers/sqlite",
  "drivers/model/glm",
  "integration/local-test-gateway",
  "harness/",
  "spikes/",
] as const;

test("prod-local-identity parses exactly one lifecycle action", () => {
  expect(parseIdentityAction(["--start"])).toBe("start");
  expect(parseIdentityAction(["--stop"])).toBe("stop");
  expect(parseIdentityAction(["--status"])).toBe("status");
  expect(parseIdentityAction(["--mint"])).toBe("mint");
  expect(parseIdentityAction([])).toBeNull();
  expect(parseIdentityAction(["--start", "--stop"])).toBeNull();
  expect(parseIdentityAction(["--local-identity"])).toBeNull();
  expect(PROD_LOCAL_IDENTITY_USAGE).toContain("--start");
});

test("prod-local-identity pins an owned Auth-only emulator config", () => {
  const config = firebaseEmulatorConfig();
  expect(config.emulators.auth.port).toBe(AUTH_EMULATOR_PORT);
  expect(config.emulators.auth.port).not.toBe(9099);
  expect(config.emulators.ui.enabled).toBe(false);
  expect(FIREBASE_AUTH_EMULATOR_HOST_VALUE).toBe(`127.0.0.1:${AUTH_EMULATOR_PORT}`);
  expect(LOCAL_FIREBASE_PROJECT_ID).toBe("omi-local-pg");
  const source = readFileSync(new URL("./prod-local-identity.ts", import.meta.url), "utf8");
  expect(source).toContain("npx --yes firebase-tools");
  expect(source).toContain("--only auth");
  expect(source).toContain("IDENTITY_FIREBASE_JSON");
  expect(source).toContain("/firebase.json");
  expect(source).toContain("pgrep");
  expect(source).toContain("accounts:signUp");
  expect(source).toContain("worthless off this machine");
});

test("prod-local-identity refuses mint against a down emulator host", async () => {
  try {
    await mintEmulatorIdentity("127.0.0.1:1");
    throw new Error("mint should have failed");
  } catch (error) {
    expect(error).toBeInstanceOf(Error);
  }
});

test("prod-local-identity value-import closure stays outside the rule-18 forbidden set", () => {
  const result = spawnSync("bun", [
    "run",
    "scripts/trace-value-imports.ts",
    "scripts/prod-local-identity.ts",
    ...FORBIDDEN.flatMap((needle) => ["--forbid", needle]),
  ], {
    cwd: platformRoot,
    encoding: "utf8",
  });
  expect(result.status).toBe(0);
  expect(`${result.stdout}${result.stderr}`).not.toContain("FORBIDDEN");
});
