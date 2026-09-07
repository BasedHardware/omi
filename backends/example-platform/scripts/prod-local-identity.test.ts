import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";
import { readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  AUTH_EMULATOR_PORT,
  IDENTITY_FIREBASE_JSON,
  portHeld,
  signalOwnedEmulator,
  withIdentityLease,
  emulatorChildEnvironment,
  assertIdentityRuntime,
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
  expect(source).toContain("installedFirebaseCli()");
  expect(source).toContain("IDENTITY_FIREBASE_JSON");
  expect(source).toContain("/firebase.json");
  expect(source).toContain("accounts:signUp");
  expect(source).toContain("worthless off this machine");
});

test("prod-local-identity refuses mint against a down emulator host", async () => {
  await expect(mintEmulatorIdentity("127.0.0.1:1")).rejects.toThrow();
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


test("identity port probe detects an occupied loopback socket without process enumeration", () => {
  const listener = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response("fixture") });
  try { expect(portHeld(listener.port!)).toBe(true); } finally { listener.stop(true); }
});

test("identity shutdown refuses a recycled PID owned by an unrelated real child", async () => {
  const child = Bun.spawn([process.execPath, "-e", "setInterval(() => {}, 1000)"], { stdout: "ignore", stderr: "ignore" });
  try {
    expect(() => signalOwnedEmulator({ version: "omi-prod-local-identity-v1", pid: child.pid,
      authPort: AUTH_EMULATOR_PORT, configPath: IDENTITY_FIREBASE_JSON }, "SIGTERM"))
      .toThrow("refusing to signal");
    expect(() => process.kill(child.pid, 0)).not.toThrow();
  } finally { child.kill(); await child.exited; }
});


test("identity lifecycle lease excludes competing starts and releases after failed ownership", async () => {
  const directory = mkdtempSync(join(tmpdir(), "identity-lease-test-"));
  try {
    await withIdentityLease(async token => {
      await expect(withIdentityLease(async () => { throw new Error("must not enter"); }, undefined, directory)).rejects.toMatchObject({ code: "EEXIST" });
      await expect(withIdentityLease(async () => "same owner", token, directory)).resolves.toBe("same owner");
      await expect(withIdentityLease(async () => "foreign", crypto.randomUUID(), directory)).rejects.toThrow("invalid inherited");
    }, undefined, directory);
    await expect(withIdentityLease(async () => { throw new Error("start failed"); }, undefined, directory)).rejects.toThrow("start failed");
    expect(await withIdentityLease(async () => "released", undefined, directory)).toBe("released");
  } finally { rmSync(directory, { recursive: true, force: true }); }
});


test("Auth-only emulator uses a child-only executable path while preserving the parent", () => {
  const parent = { PATH: "/usr/bin:/bin", FIXTURE: "retained" };
  const child = emulatorChildEnvironment(parent, "/owned/bun/bin/bun");
  expect(child.PATH).toBe("/owned/bun/bin");
  expect(parent.PATH).toBe("/usr/bin:/bin");
  expect(child.FIXTURE).toBe("retained");
  expect(child.FIREBASE_AUTH_EMULATOR_HOST).toBe(FIREBASE_AUTH_EMULATOR_HOST_VALUE);
});


test("Auth emulator startup enforces the project runtime pin before creating a child", () => {
  expect(() => assertIdentityRuntime("1.3.14")).not.toThrow();
  expect(() => assertIdentityRuntime("1.4.0")).toThrow("project-pinned bun@1.3.14");
});
