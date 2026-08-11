// LIFECYCLE: permanent

import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, test } from "node:test";

const stack = new URL("./dev-stack.sh", import.meta.url).pathname;
let scratch;
let listeners;
beforeEach(() => { scratch = mkdtempSync(join(tmpdir(), "omi-dev-stack-cli-")); listeners = []; });
afterEach(() => {
  for (const listener of listeners) {
    try { listener.kill("SIGKILL"); } catch {}
  }
  rmSync(scratch, { recursive: true, force: true });
});

function roots() {
  const core = join(scratch, "core-root");
  const platform = join(scratch, "platform-root");
  mkdirSync(join(platform, "apps/service/bin"), { recursive: true });
  mkdirSync(core, { recursive: true });
  writeFileSync(join(platform, "apps/service/bin/dev-server.ts"), "// must never execute in occupancy tests\n");
  return { core, platform };
}

async function occupy(port) {
  const existing = spawnSync("lsof", ["-t", `-iTCP:${port}`, "-sTCP:LISTEN"], { encoding: "utf8" }).stdout
    .trim().split(/\s+/u).filter(Boolean).map(Number);
  if (existing.length > 0) return existing;
  const child = spawn(process.execPath, ["-e", `require("net").createServer().listen(${port},"127.0.0.1")`], { stdio: "ignore" });
  listeners.push(child);
  await new Promise((resolve, reject) => {
    child.once("error", reject);
    setTimeout(resolve, 100);
  });
  const owned = spawnSync("lsof", ["-t", `-iTCP:${port}`, "-sTCP:LISTEN"], { encoding: "utf8" }).stdout
    .trim().split(/\s+/u).filter(Boolean).map(Number);
  assert.ok(owned.includes(child.pid), `test listener did not bind ${port}`);
  return owned;
}

function run(args, rootPair = roots()) {
  return spawnSync(stack, args, {
    encoding: "utf8",
    env: {
      ...process.env,
      OMI_CORE_ROOT: rootPair.core,
      OMI_PLATFORM_ROOT: rootPair.platform,
      OMI_DEV_STACK_RUNDIR: join(scratch, "run-root"),
    },
  });
}

test("RED-PROOF stack rejects unsafe, reserved, overflow, and shell-attributed run ids before launch", () => {
  for (const runId of ["anonymous", "overflow", "__private", "a".repeat(97), "run::macos", "run::ios"]) {
    const result = run(["--up", "--run-id", runId]);
    assert.notEqual(result.status, 0, runId);
    assert.match(result.stderr, /raw bounded|reserved|transport/);
    assert.doesNotMatch(result.stdout + result.stderr, /service-ready/);
  }
});

test("RED-PROOF occupied 5290 is named and never killed or replaced", async () => {
  const listenerPids = await occupy(5290);
  const result = run(["--assert", "--run-id", "run-occupied-5290"]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /required port 5290 is occupied/);
  assert.doesNotMatch(result.stdout + result.stderr, /service-ready/);
  for (const pid of listenerPids) assert.doesNotThrow(() => process.kill(pid, 0));
});

test("RED-PROOF occupied 4851 refuses a second service listener and preserves its owner", async () => {
  const listenerPids = await occupy(4851);
  const result = run(["--up", "--run-id", "run-occupied-4851"]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /required port 4851 is occupied.*not kill it or start a second listener/s);
  for (const pid of listenerPids) assert.doesNotThrow(() => process.kill(pid, 0));
});
