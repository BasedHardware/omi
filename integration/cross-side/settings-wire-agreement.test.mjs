/**
 * Cross-side agreement for the ratified optional-auth Settings seam.
 *
 * The consumer is the built production adapter. The producer is the registered
 * platform app, booted as its real loopback service in a separate process. The
 * one ordered test keeps session revocation last so every assertion observes a
 * single service lifetime and the exact token the child announced.
 */

import { spawn } from "node:child_process";
import { once } from "node:events";
import assert from "node:assert/strict";
import { after, before, test } from "node:test";

const {
  deletePlatformCurrentSession,
  fetchPlatformSettings,
  PLATFORM_CURRENT_SESSION_PATH,
  PLATFORM_SETTINGS_PATH,
} = await import(new URL("../../core/packages/adapters-platform/dist/index.js", import.meta.url).href);
const { REPO_PATHS } = await import(new URL("../lib/provenance.mjs", import.meta.url).href);

const PLATFORM_REPO = REPO_PATHS.platform;
const BOOT_TIMEOUT_MS = 20_000;

let child;
let baseUrl;
let token;

function realHttpClient(credential) {
  const calls = [];
  return {
    calls,
    async request(method, path, body) {
      calls.push({ method, path, body });
      const response = await fetch(`${baseUrl}${path}`, {
        method,
        headers: {
          ...(credential === null ? {} : { authorization: `Bearer ${credential}` }),
          ...(body === undefined ? {} : { "content-type": "application/json" }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      const text = await response.text();
      let json = null;
      try { json = JSON.parse(text); } catch { /* 204 has no body. */ }
      return { status: response.status, json, text };
    },
  };
}

async function readStats() {
  const response = await fetch(`${baseUrl}/v1/qa/status`);
  const body = await response.json();
  return {
    servedReads: body.served.domainReadsServed,
    processStamp: JSON.stringify(body.seed),
  };
}

before(async () => {
  child = spawn("bun", ["run", "integration/control/live-service.ts"], {
    cwd: PLATFORM_REPO,
    env: { ...process.env, TZ: "UTC" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });

  const deadline = Date.now() + BOOT_TIMEOUT_MS;
  while (Date.now() < deadline) {
    for (const line of stdout.split("\n")) {
      if (!line.includes("live_service_listening")) continue;
      try {
        const event = JSON.parse(line);
        if (event.event === "live_service_listening" && typeof event.url === "string") {
          baseUrl = event.url;
          token = event.devToken;
        }
      } catch { /* Ignore a partial stdout line. */ }
    }
    if (baseUrl !== undefined) return;
    if (child.exitCode !== null) {
      throw new Error(`platform exited before readiness (${child.exitCode})\n${stderr}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`platform never announced readiness\n${stderr}`);
});

after(async () => {
  if (child && child.exitCode === null) {
    child.kill();
    await once(child, "exit");
  }
});

test("the built Settings client preserves optional auth and current-session revocation over real HTTP", async () => {
  const before = await readStats();

  const absent = realHttpClient(null);
  assert.deepEqual(await fetchPlatformSettings(absent), {
    kind: "snapshot",
    snapshot: { identity: null, entitlement: null },
  });

  const invalid = realHttpClient("present-but-invalid");
  assert.deepEqual(await fetchPlatformSettings(invalid), { kind: "auth-invalid", status: 401 });

  const signedIn = realHttpClient(token);
  assert.deepEqual(await fetchPlatformSettings(signedIn), {
    kind: "snapshot",
    snapshot: {
      identity: { displayName: "local-dev-user", email: "" },
      entitlement: null,
    },
  });

  assert.deepEqual(await deletePlatformCurrentSession(signedIn), { ok: true });
  assert.deepEqual(await fetchPlatformSettings(signedIn), { kind: "auth-invalid", status: 401 });
  assert.deepEqual(await deletePlatformCurrentSession(signedIn), { ok: true });

  assert.deepEqual(absent.calls, [{ method: "GET", path: PLATFORM_SETTINGS_PATH, body: undefined }]);
  assert.deepEqual(signedIn.calls, [
    { method: "GET", path: PLATFORM_SETTINGS_PATH, body: undefined },
    { method: "DELETE", path: PLATFORM_CURRENT_SESSION_PATH, body: undefined },
    { method: "GET", path: PLATFORM_SETTINGS_PATH, body: undefined },
    { method: "DELETE", path: PLATFORM_CURRENT_SESSION_PATH, body: undefined },
  ]);

  const after = await readStats();
  assert.equal(after.processStamp, before.processStamp, "the platform restarted during the proof");
  assert.equal(after.servedReads - before.servedReads, 2,
    "only signed-out and accepted signed-in reads may advance the producer served counter");

  // red-proof: sending a bearer for the absent read makes the first snapshot
  // auth-invalid. Treating a real 401 as signed-out breaks both invalid reads.
  // Adding any DELETE body makes the real route return 400. A stale adapter
  // build breaks these observations even if the source parser looks correct.
});
