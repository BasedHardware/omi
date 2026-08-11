// LIFECYCLE: permanent

import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, test } from "node:test";

import { EXPECTED_COMMAND, PROCESS_OWNER_SCHEMA, processSnapshot } from "./process-owner.mjs";
import { SERVICE_BASE_URL, SERVICE_EXECUTABLE, SERVICE_READINESS_SCHEMA } from "./evidence-matrix.mjs";

const cli = new URL("./process-owner.mjs", import.meta.url);
let scratch;
let children;
beforeEach(() => { scratch = mkdtempSync(join(tmpdir(), "omi-owner-test-")); children = []; });
afterEach(() => {
  for (const child of children) {
    try { child.kill("SIGKILL"); } catch {}
  }
  rmSync(scratch, { recursive: true, force: true });
});

test("RED-PROOF stale/reused/unknown owner PID is skipped and the unrelated process survives", async () => {
  const unrelated = spawn("sleep", ["30"], { stdio: "ignore" });
  children.push(unrelated);
  await new Promise((resolve) => unrelated.once("spawn", resolve));
  const snapshot = processSnapshot(unrelated.pid);
  assert.ok(snapshot);
  const databasePath = join(scratch, "service.sqlite");
  const readinessPath = join(scratch, "readiness.json");
  writeFileSync(readinessPath, `${JSON.stringify({
    schema: SERVICE_READINESS_SCHEMA,
    runId: "run-owner-test",
    executable: SERVICE_EXECUTABLE,
    baseUrl: SERVICE_BASE_URL,
    databasePath,
    pid: unrelated.pid,
    evidencePath: "/v1/qa/evidence",
    devToken: "local-token",
    ownerAccountId: "local-owner",
  })}\n`);
  const ownerPath = join(scratch, "owner.json");
  writeFileSync(ownerPath, `${JSON.stringify({
    schema: PROCESS_OWNER_SCHEMA,
    runId: "run-owner-test",
    pid: unrelated.pid,
    expectedExecutable: SERVICE_EXECUTABLE,
    expectedCommand: EXPECTED_COMMAND,
    ownerToken: "a".repeat(32),
    processStartIdentity: `${snapshot.startIdentity}-stale`,
    databasePath,
    readinessPath,
  })}\n`);

  const result = spawnSync(process.execPath, [cli.pathname, "stop", "--record", ownerPath], { encoding: "utf8" });
  assert.equal(result.status, 3);
  assert.match(result.stdout, /stale start identity|unknown executable or command/);
  assert.doesNotThrow(() => process.kill(unrelated.pid, 0));
});
