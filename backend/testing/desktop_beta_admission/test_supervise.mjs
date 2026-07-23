import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import test from "node:test";

const directory = new URL(".", import.meta.url).pathname;
const supervisor = join(directory, "supervise.mjs");
const configWriter = join(directory, "emulator_config.mjs");
const fixture = join(directory, "test_fixtures", "process_tree.mjs");

function temporaryDirectory() {
  return mkdtempSync(join(tmpdir(), "omi-desktop-beta-admission-test-"));
}

function isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    throw error;
  }
}

async function waitFor(check, description) {
  const deadline = Date.now() + 3_000;
  while (!check()) {
    if (Date.now() > deadline) throw new Error(`Timed out waiting for ${description}`);
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

function exactKill(pid) {
  if (pid && isAlive(pid)) process.kill(pid, "SIGKILL");
}

async function run(command, args) {
  const child = spawn(command, args, { stdio: "ignore" });
  return await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, receivedSignal) => resolve({ code, signal: receivedSignal }));
  });
}

function grandchildPid(pidFile) {
  return Number(readFileSync(pidFile, "utf8").trim());
}

test("an unsupervised parent leaves its grandchild alive, while the supervisor drains its group", async () => {
  const temp = temporaryDirectory();
  const oldPidFile = join(temp, "old.pid");
  const newPidFile = join(temp, "new.pid");
  const cleanupPath = join(temp, "owned-runtime");
  let oldPid;
  try {
    await run(process.execPath, [fixture, oldPidFile, "exit"]);
    oldPid = grandchildPid(oldPidFile);
    assert.equal(isAlive(oldPid), true, "old immediate-parent cleanup leaves the grandchild alive");

    mkdirSync(cleanupPath);
    const result = await run(process.execPath, [
      supervisor,
      "--timeout-ms",
      "1000",
      "--grace-ms",
      "100",
      "--cleanup-path",
      cleanupPath,
      "--",
      process.execPath,
      fixture,
      newPidFile,
      "exit",
    ]);
    assert.equal(result.code, 0);
    const newPid = grandchildPid(newPidFile);
    await waitFor(() => !isAlive(newPid), "supervised grandchild cleanup");
    assert.equal(existsSync(cleanupPath), false, "the runner removes its owned temporary directory");
  } finally {
    exactKill(oldPid);
    rmSync(temp, { recursive: true, force: true });
  }
});

test("cleanup leaves a non-owned process untouched", async () => {
  const temp = temporaryDirectory();
  const ownedPidFile = join(temp, "owned.pid");
  const unrelatedPidFile = join(temp, "unrelated.pid");
  let unrelatedPid;
  let unrelatedParent;
  try {
    unrelatedParent = spawn(process.execPath, [fixture, unrelatedPidFile, "wait"], { stdio: "ignore" });
    await waitFor(() => existsSync(unrelatedPidFile), "unrelated fixture readiness");
    unrelatedPid = grandchildPid(unrelatedPidFile);

    await run(process.execPath, [supervisor, "--timeout-ms", "1000", "--grace-ms", "100", "--", process.execPath, fixture, ownedPidFile, "exit"]);
    await waitFor(() => !isAlive(grandchildPid(ownedPidFile)), "owned grandchild cleanup");
    assert.equal(isAlive(unrelatedParent.pid), true);
    assert.equal(isAlive(unrelatedPid), true);
  } finally {
    exactKill(unrelatedParent?.pid);
    exactKill(unrelatedPid);
    rmSync(temp, { recursive: true, force: true });
  }
});

test("each emulator config has explicit, isolated API and websocket ports", async () => {
  const temp = temporaryDirectory();
  try {
    const configs = [join(temp, "one.json"), join(temp, "two.json")];
    const ports = [];
    for (const config of configs) {
      const result = await run(process.execPath, [configWriter, config]);
      assert.equal(result.code, 0);
      const firestore = JSON.parse(readFileSync(config, "utf8")).emulators.firestore;
      assert.equal(firestore.host, "127.0.0.1");
      assert.notEqual(firestore.port, firestore.websocketPort);
      assert.notEqual(firestore.websocketPort, 9150);
      assert.notEqual(firestore.websocketPort, 9151);
      ports.push(firestore.port, firestore.websocketPort);
    }
    assert.equal(new Set(ports).size, ports.length);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
});

for (const [label, trigger, expectedCode, timeoutMs] of [
  ["timeout", undefined, 124, "1000"],
  ["SIGTERM", { signal: "SIGTERM", readyFile: null }, 143, "5000"],
]) {
  test(`${label} drains emulator children`, async () => {
    const temp = temporaryDirectory();
    const pidFile = join(temp, "child.pid");
    const args = [supervisor, "--timeout-ms", timeoutMs, "--grace-ms", "100", "--", process.execPath, fixture, pidFile, "wait"];
    const child = spawn(process.execPath, args, { stdio: "ignore" });
    try {
      await waitFor(() => existsSync(pidFile), "owned fixture readiness");
      if (trigger) child.kill(trigger.signal);
      const result = await new Promise((resolve, reject) => {
        child.once("error", reject);
        child.once("exit", (code, signal) => resolve({ code, signal }));
      });
      assert.equal(result.code, expectedCode);
      await waitFor(() => !isAlive(grandchildPid(pidFile)), `${label} cleanup`);
    } finally {
      exactKill(child.pid);
      rmSync(temp, { recursive: true, force: true });
    }
  });
}
