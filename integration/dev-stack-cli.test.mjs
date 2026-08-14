// LIFECYCLE: permanent

import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
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
  const runRoot = join(scratch, "run-root");
  const pidPath = join(runRoot, "local-test-gateway.pid");
  if (existsSync(pidPath)) {
    const pid = Number(readFileSync(pidPath, "utf8").trim());
    if (Number.isInteger(pid) && pid > 0) {
      try { process.kill(pid, "SIGKILL"); } catch {}
    }
  }
  const ownerPath = join(runRoot, "service-owner.json");
  if (existsSync(ownerPath)) {
    try {
      const owner = JSON.parse(readFileSync(ownerPath, "utf8"));
      if (Number.isInteger(owner.pid) && owner.pid > 0) process.kill(owner.pid, "SIGKILL");
    } catch {}
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
  const existing = portPids(port);
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

function portPids(port) {
  return spawnSync("lsof", ["-t", `-iTCP:${port}`, "-sTCP:LISTEN"], { encoding: "utf8" }).stdout
    .trim().split(/\s+/u).filter(Boolean).map(Number);
}

function processIdsMatching(fragment) {
  return spawnSync("pgrep", ["-f", fragment], { encoding: "utf8" }).stdout
    .trim().split(/\s+/u).filter(Boolean).map(Number);
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

test("RED-PROOF a claimed raw run id is exclusive and prior evidence is never overwritten", () => {
  const rootPair = roots();
  const runRoot = join(scratch, "run-root");
  const priorRun = join(runRoot, "runs", "reused-run");
  mkdirSync(join(priorRun, "logs"), { recursive: true });
  const sentinel = join(priorRun, "prior-evidence.json");
  const readiness = join(priorRun, "service-readiness.json");
  writeFileSync(sentinel, "{\"prior\":true}\n");
  writeFileSync(readiness, "{\"stale\":true}\n");
  const beforeFiles = readdirSync(priorRun).sort();
  const listenersBefore = portPids(4851);

  const result = run(["--up", "--run-id", "reused-run"], rootPair);

  assert.equal(result.status, 1);
  assert.match(result.stderr, /already owns a run directory.*refusing to reuse or overwrite prior evidence/);
  assert.doesNotMatch(result.stdout + result.stderr, /service-ready/);
  assert.equal(readFileSync(sentinel, "utf8"), "{\"prior\":true}\n");
  assert.equal(readFileSync(readiness, "utf8"), "{\"stale\":true}\n");
  assert.deepEqual(readdirSync(priorRun).sort(), beforeFiles);
  assert.equal(existsSync(join(runRoot, "service-owner.json")), false);
  assert.deepEqual(portPids(4851), listenersBefore);
});

function writeService(rootPair, runIdExpr) {
  writeFileSync(join(rootPair.platform, "apps/service/bin/dev-server.ts"), `
    import { writeFileSync } from "node:fs";
    const port = Number(process.env.OMI_PORT);
    Bun.serve({ hostname: "127.0.0.1", port, fetch(request) {
      return new URL(request.url).pathname === "/ready" ? new Response("ok") : new Response("missing", { status: 404 });
    }});
    writeFileSync(process.env.OMI_DEV_READY_RECORD, JSON.stringify({
      schema: "omi.dev-service-readiness.v1",
      runId: ${runIdExpr},
      executable: "apps/service/bin/dev-server.ts",
      baseUrl: "http://127.0.0.1:4851",
      databasePath: process.env.OMI_QA_DB,
      pid: process.pid,
      evidencePath: "/v1/qa/evidence",
      devToken: "new-failed-run-secret",
      ownerAccountId: "local-owner",
    }) + "\\n");
    console.log("token=new-failed-run-secret http://127.0.0.1:4851 Authorization: Bearer new-failed-run-secret");
  `);
}

test("RED-PROOF mismatched readiness cleans up the exact service and logger process tree", () => {
  const rootPair = roots();
  writeService(rootPair, '"stale-other-run"');
  const runRoot = join(scratch, "run-root");
  const listenersBefore = portPids(4851);
  const gatewayBefore = portPids(8788);

  const result = run(["--up", "--run-id", "expected-run"], rootPair);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /wrong runId/);
  assert.doesNotMatch(result.stdout + result.stderr, /service-ready/);
  assert.deepEqual(portPids(4851), listenersBefore);
  assert.deepEqual(portPids(8788), gatewayBefore);
  assert.deepEqual(processIdsMatching(`${runRoot}/runs/expected-run/logs/service.log`), []);
  assert.equal(existsSync(join(runRoot, "service-owner.json")), false);
  const logPath = join(runRoot, "runs", "expected-run", "logs", "service.log");
  assert.equal(existsSync(join(runRoot, "runs", "expected-run")), true);
  assert.equal(existsSync(logPath), true);
  assert.doesNotMatch(readFileSync(logPath, "utf8"), /new-failed-run-secret/);
});

test("RED-PROOF --stop frees the local test gateway this harness started", () => {
  const rootPair = roots();
  writeService(rootPair, "process.env.OMI_RUN_ID");
  const gatewayBefore = portPids(8788);
  const serviceBefore = portPids(4851);

  const up = run(["--up", "--run-id", "run-stop-gateway"], rootPair);
  assert.equal(up.status, 0, `${up.stdout}${up.stderr}`);
  assert.match(up.stdout, /service-ready/);
  assert.ok(portPids(8788).length > 0);

  const stop = run(["--stop"], rootPair);
  assert.equal(stop.status, 0, `${stop.stdout}${stop.stderr}`);
  assert.deepEqual(portPids(8788), gatewayBefore);
  assert.deepEqual(portPids(4851), serviceBefore);
});

test("RED-PROOF --stop refuses a gateway it did not start", async () => {
  const listenerPids = await occupy(8788);
  const result = run(["--stop"]);
  for (const pid of listenerPids) assert.doesNotThrow(() => process.kill(pid, 0));
  assert.deepEqual(portPids(8788), listenerPids);
  void result;
});

test("RED-PROOF a failed assert leaves the sanitized run log readable", () => {
  const rootPair = roots();
  writeService(rootPair, "process.env.OMI_RUN_ID");
  mkdirSync(join(rootPair.core, "core/packages/surfaces"), { recursive: true });
  mkdirSync(join(rootPair.core, "core/shells/macos/scripts"), { recursive: true });
  mkdirSync(join(rootPair.core, "core/shells/ios/scripts"), { recursive: true });
  const macos = join(rootPair.core, "core/shells/macos/scripts/dev-run-macos.sh");
  const ios = join(rootPair.core, "core/shells/ios/scripts/dev-run-ios.sh");
  writeFileSync(macos, "#!/bin/bash\nexit 1\n");
  writeFileSync(ios, "#!/bin/bash\nexit 1\n");
  chmodSync(macos, 0o755);
  chmodSync(ios, 0o755);
  writeFileSync(join(rootPair.core, "core/package.json"), "{not-json");

  const result = run(["--assert", "--run-id", "run-keep-logs"], rootPair);
  assert.notEqual(result.status, 0, `${result.stdout}${result.stderr}`);
  assert.match(result.stderr, /core workspace build failed|see the run-scoped core build log/);
  const logPath = join(scratch, "run-root", "runs", "run-keep-logs", "logs", "core-build.log");
  assert.equal(existsSync(logPath), true, `${result.stdout}${result.stderr}`);
  assert.match(readFileSync(logPath, "utf8"), /\S/, `${result.stdout}${result.stderr}`);
});
