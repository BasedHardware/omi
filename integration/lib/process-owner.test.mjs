// LIFECYCLE: permanent

import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, test } from "node:test";

import { EXPECTED_COMMAND, PROCESS_OWNER_SCHEMA, ownerBindingPath, processSnapshot } from "./process-owner.mjs";
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

test("RED-PROOF a valid-format replacement owner token cannot signal the verified service", async () => {
  const owned = spawn("bun", ["-e", "setInterval(() => {}, 1000)", SERVICE_EXECUTABLE], { stdio: "ignore" });
  children.push(owned);
  await new Promise((resolve) => owned.once("spawn", resolve));
  const snapshot = processSnapshot(owned.pid);
  assert.ok(snapshot);

  const databasePath = join(scratch, "service.sqlite");
  const readinessPath = join(scratch, "readiness.json");
  const ownerPath = join(scratch, "owner.json");
  const originalToken = "a".repeat(32);
  writeFileSync(readinessPath, `${JSON.stringify({
    schema: SERVICE_READINESS_SCHEMA,
    runId: "run-token-binding",
    executable: SERVICE_EXECUTABLE,
    baseUrl: SERVICE_BASE_URL,
    databasePath,
    pid: owned.pid,
    evidencePath: "/v1/qa/evidence",
    devToken: "local-token",
    ownerAccountId: "local-owner",
  })}\n`);

  const written = spawnSync(process.execPath, [
    cli.pathname, "write", "--record", ownerPath,
    "--run-id", "run-token-binding", "--pid", String(owned.pid),
    "--owner-token", originalToken, "--start-identity", snapshot.startIdentity,
    "--database", databasePath, "--readiness", readinessPath,
  ], { encoding: "utf8" });
  assert.equal(written.status, 0, written.stderr);
  assert.equal(Object.keys(JSON.parse(readFileSync(ownerPath, "utf8"))).length, 9);
  assert.equal(existsSync(ownerBindingPath(ownerPath)), true);
  assert.equal(statSync(ownerBindingPath(ownerPath)).mode & 0o777, 0o600);
  assert.doesNotMatch(readFileSync(ownerBindingPath(ownerPath), "utf8"), new RegExp(originalToken));

  const changed = JSON.parse(readFileSync(ownerPath, "utf8"));
  changed.ownerToken = "b".repeat(32);
  writeFileSync(ownerPath, `${JSON.stringify(changed, null, 2)}\n`);

  const refused = spawnSync(process.execPath, [cli.pathname, "stop", "--record", ownerPath], { encoding: "utf8" });
  assert.equal(refused.status, 3);
  assert.match(refused.stdout, /owner binding ownerTokenSha256 does not match/);
  assert.doesNotThrow(() => process.kill(owned.pid, 0));

  changed.ownerToken = originalToken;
  writeFileSync(ownerPath, `${JSON.stringify(changed, null, 2)}\n`);
  const stopped = spawnSync(process.execPath, [cli.pathname, "stop", "--record", ownerPath], { encoding: "utf8" });
  assert.equal(stopped.status, 0, stopped.stderr || stopped.stdout);
  assert.match(stopped.stdout, /"stopped":true/);
  assert.equal(processSnapshot(owned.pid), null);
});
