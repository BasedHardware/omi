// LIFECYCLE: permanent

import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { test } from "node:test";

import { processSnapshot } from "./process-owner.mjs";

const EXECUTABLE = "apps/service/bin/dev-server.ts";
const BASE_URL = "http://127.0.0.1:4851";
const EVIDENCE_PATH = "/v1/qa/evidence";

function streamArgs(cli, { output, readiness, readyOut, runId, database, pid, startIdentity }) {
  return [
    cli, "--stream", "--out", output, "--readiness", readiness, "--ready-out", readyOut,
    "--run-id", runId, "--executable", EXECUTABLE, "--base-url", BASE_URL,
    "--database", database, "--pid", String(pid), "--process-start-identity", startIdentity,
  ];
}

function readinessRecord({ runId, database, pid, token }) {
  return {
    schema: "omi.dev-service-readiness.v1",
    runId,
    executable: EXECUTABLE,
    baseUrl: BASE_URL,
    databasePath: database,
    pid,
    evidencePath: EVIDENCE_PATH,
    devToken: token,
    ownerAccountId: "local-owner",
  };
}

test("launcher logs retain diagnostics but remove credentials and every base URL", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-sanitize-log-"));
  try {
    const input = join(scratch, "raw.log");
    const output = join(scratch, "safe.log");
    writeFileSync(input, "launch http://127.0.0.1:4851/path token-marker Authorization: Bearer another-secret\nkept diagnostic\n");
    const cli = new URL("./sanitize-log.mjs", import.meta.url).pathname;
    const result = spawnSync(process.execPath, [cli, "--in", input, "--out", output, "--redact", "token-marker"], { encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    const safe = readFileSync(output, "utf8");
    assert.match(safe, /kept diagnostic/);
    assert.doesNotMatch(safe, /127\.0\.0\.1|token-marker|another-secret/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("service output is sanitized before persistence using the independent readiness record", async () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-stream-sanitize-log-"));
  const service = spawn("bun", ["-e", "setInterval(() => {}, 1000)", EXECUTABLE], { stdio: "ignore" });
  try {
    await new Promise((resolve) => service.once("spawn", resolve));
    const snapshot = processSnapshot(service.pid);
    assert.ok(snapshot);
    const token = "stream-secret-token";
    const readiness = join(scratch, "readiness.json");
    const output = join(scratch, "service.log");
    const readyOut = join(scratch, "sanitizer-ready");
    const database = join(scratch, "service.sqlite");
    const pid = service.pid;
    writeFileSync(readiness, `${JSON.stringify(readinessRecord({ runId: "stream-run", database, pid, token }))}\n`);
    const cli = new URL("./sanitize-log.mjs", import.meta.url).pathname;
    const result = spawnSync(process.execPath, streamArgs(cli, {
      output, readiness, readyOut, runId: "stream-run", database, pid, startIdentity: snapshot.startIdentity,
    }), {
      encoding: "utf8",
      input: `service http://127.0.0.1:4851 token=${token}\nAuthorization: Bearer ${token}\nkept diagnostic\n`,
    });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(existsSync(readyOut), true);
    assert.equal(statSync(output).mode & 0o777, 0o600);
    const safe = readFileSync(output, "utf8");
    assert.match(safe, /kept diagnostic/);
    assert.doesNotMatch(safe, /127\.0\.0\.1|stream-secret-token/);
  } finally {
    try { service.kill("SIGKILL"); } catch {}
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("service output fails closed when no readiness identity exists", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-stream-sanitize-fail-"));
  try {
    const output = join(scratch, "service.log");
    const cli = new URL("./sanitize-log.mjs", import.meta.url).pathname;
    const snapshot = processSnapshot(process.pid);
    assert.ok(snapshot);
    const result = spawnSync(process.execPath, streamArgs(cli, {
      output,
      readiness: join(scratch, "absent.json"),
      readyOut: join(scratch, "never-ready"),
      runId: "absent-run",
      database: join(scratch, "service.sqlite"),
      pid: process.pid,
      startIdentity: snapshot.startIdentity,
    }), { encoding: "utf8", input: "raw-unproven-secret diagnostics\n" });
    assert.equal(result.status, 0, result.stderr);
    const safe = readFileSync(output, "utf8");
    assert.match(safe, /diagnostics withheld/);
    assert.doesNotMatch(safe, /raw-unproven-secret/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("RED-PROOF stale readiness cannot activate or persist the new token even transiently", async () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-stream-sanitize-stale-"));
  const service = spawn("bun", ["-e", "setInterval(() => {}, 1000)", EXECUTABLE], { stdio: "ignore" });
  try {
    await new Promise((resolve) => service.once("spawn", resolve));
    const snapshot = processSnapshot(service.pid);
    assert.ok(snapshot);
    const readiness = join(scratch, "readiness.json");
    const output = join(scratch, "service.log");
    const readyOut = join(scratch, "sanitizer-ready");
    const database = join(scratch, "new-service.sqlite");
    const newToken = "new-startup-secret";
    writeFileSync(readiness, `${JSON.stringify(readinessRecord({
      runId: "stale-run",
      database: join(scratch, "stale-service.sqlite"),
      pid: 1111,
      token: "stale-secret",
    }))}\n`);

    const cli = new URL("./sanitize-log.mjs", import.meta.url).pathname;
    const child = spawn(process.execPath, streamArgs(cli, {
      output, readiness, readyOut, runId: "new-run", database, pid: service.pid,
      startIdentity: snapshot.startIdentity,
    }), { stdio: ["pipe", "pipe", "pipe"] });
    child.stdin.write(`new service token=${newToken} ${BASE_URL}\n`);
    await new Promise((resolve) => setTimeout(resolve, 100));

    assert.equal(existsSync(output), true);
    assert.equal(readFileSync(output, "utf8"), "", "raw bytes reached disk before exact readiness activation");
    assert.equal(existsSync(readyOut), false);

    child.stdin.end();
    const exitCode = await new Promise((resolve) => child.once("close", resolve));
    assert.equal(exitCode, 0);
    const final = readFileSync(output, "utf8");
    assert.match(final, /diagnostics withheld/);
    assert.doesNotMatch(final, /new-startup-secret|stale-secret|127\.0\.0\.1/);
  } finally {
    try { service.kill("SIGKILL"); } catch {}
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("RED-PROOF logger self-terminates when its exact service process identity ends", async () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-stream-sanitize-owner-"));
  const service = spawn("bun", ["-e", "setInterval(() => {}, 1000)", EXECUTABLE], { stdio: "ignore" });
  let logger;
  try {
    await new Promise((resolve) => service.once("spawn", resolve));
    const snapshot = processSnapshot(service.pid);
    assert.ok(snapshot);
    const readiness = join(scratch, "readiness.json");
    const output = join(scratch, "service.log");
    const readyOut = join(scratch, "sanitizer-ready");
    const database = join(scratch, "service.sqlite");
    const token = "self-fenced-secret";
    writeFileSync(readiness, `${JSON.stringify(readinessRecord({
      runId: "self-fenced-run", database, pid: service.pid, token,
    }))}\n`);
    const cli = new URL("./sanitize-log.mjs", import.meta.url).pathname;
    logger = spawn(process.execPath, streamArgs(cli, {
      output, readiness, readyOut, runId: "self-fenced-run", database,
      pid: service.pid, startIdentity: snapshot.startIdentity,
    }), { stdio: ["pipe", "pipe", "pipe"] });
    logger.stdin.on("error", () => {});
    logger.stdin.write(`diagnostic token=${token} ${BASE_URL}\n`);
    for (let attempt = 0; attempt < 50 && !existsSync(readyOut); attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    assert.equal(existsSync(readyOut), true);

    service.kill("SIGKILL");
    const loggerExit = await Promise.race([
      new Promise((resolve) => logger.once("close", resolve)),
      new Promise((_, reject) => setTimeout(() => reject(new Error("logger orphaned after service exit")), 2000)),
    ]);
    assert.equal(loggerExit, 0);
    const safe = readFileSync(output, "utf8");
    assert.match(safe, /diagnostic/);
    assert.doesNotMatch(safe, /self-fenced-secret|127\.0\.0\.1/);
  } finally {
    try { service.kill("SIGKILL"); } catch {}
    try { logger?.kill("SIGKILL"); } catch {}
    rmSync(scratch, { recursive: true, force: true });
  }
});
