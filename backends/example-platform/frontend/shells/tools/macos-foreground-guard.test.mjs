import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const helper = path.join(path.dirname(fileURLToPath(import.meta.url)), "macos-foreground-guard.mjs");
const guardArgs = ["--forbid-bundle-ids", "com.apple.iphonesimulator,me.omi.proto.omiWebviewProto"];

test("foreground guard runs a background CLI command without changing focus", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-focus-guard-"));
  try {
    const result = path.join(scratch, "result.json"); const stdout = path.join(scratch, "stdout"); const stderr = path.join(scratch, "stderr");
    const run = spawnSync(process.execPath, [helper, "--result", result, "--stdout", stdout, "--stderr", stderr, "--timeout", "5", ...guardArgs, "--", "/bin/sh", "-c", "printf guarded"], { encoding: "utf8" });
    assert.equal(run.status, 0, run.stderr);
    const receipt = JSON.parse(readFileSync(result, "utf8"));
    assert.equal(receipt.status, 0);
    assert.equal(receipt.monitor_error, null);
    assert.equal(receipt.target_interval_milliseconds, 20);
    assert.equal(receipt.probe_timeout_milliseconds, 250);
    assert.ok(receipt.sample_count >= 1);
    assert.ok(receipt.max_sample_gap_milliseconds >= 0);
    assert.match(receipt.policy, /^sampled-macos-forbidden-fixture-foreground-detection-/);
    assert.deepEqual(receipt.forbidden_bundle_ids, ["com.apple.iphonesimulator", "me.omi.proto.omiWebviewProto"]);
    assert.equal(readFileSync(stdout, "utf8"), "guarded");
    assert.equal(readFileSync(stderr, "utf8"), "");
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test("foreground guard refuses a forbidden frontmost bundle before starting the child", (t) => {
  const front = spawnSync("/usr/bin/lsappinfo", ["front"], { encoding: "utf8", timeout: 2_000 });
  const identity = front.status === 0 ? front.stdout.trim() : "";
  const info = identity ? spawnSync("/usr/bin/lsappinfo", ["info", "-only", "bundleID", "-app", identity], { encoding: "utf8", timeout: 2_000 }) : { status: 1, stdout: "" };
  const bundleId = info.status === 0 ? info.stdout.match(/"CFBundleIdentifier"="([A-Za-z0-9.-]+)"/)?.[1] : null;
  if (!bundleId) return t.skip("frontmost bundle identity unavailable");
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-focus-forbidden-"));
  try {
    const result = path.join(scratch, "result.json"); const stdout = path.join(scratch, "stdout"); const stderr = path.join(scratch, "stderr"); const childMarker = path.join(scratch, "child-ran");
    const run = spawnSync(process.execPath, [helper, "--result", result, "--stdout", stdout, "--stderr", stderr, "--timeout", "5", "--forbid-bundle-ids", bundleId, "--", "/usr/bin/touch", childMarker], { encoding: "utf8" });
    assert.notEqual(run.status, 0);
    const receipt = JSON.parse(readFileSync(result, "utf8"));
    assert.equal(receipt.monitor_error, "a forbidden fixture application is already foreground");
    assert.deepEqual(receipt.forbidden_bundle_ids, [bundleId]);
    assert.equal(existsSync(childMarker), false);
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test("foreground guard fails closed on timeout and writes a terminal result", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-focus-timeout-"));
  try {
    const result = path.join(scratch, "result.json"); const stdout = path.join(scratch, "stdout"); const stderr = path.join(scratch, "stderr");
    const run = spawnSync(process.execPath, [helper, "--result", result, "--stdout", stdout, "--stderr", stderr, "--timeout", "1", ...guardArgs, "--", "/bin/sh", "-c", "trap '' TERM; sleep 5"], { encoding: "utf8", timeout: 5_000 });
    assert.notEqual(run.status, 0);
    const receipt = JSON.parse(readFileSync(result, "utf8"));
    assert.equal(receipt.monitor_error, "guarded command timed out");
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test("foreground guard bounds noisy child output and fails closed", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-focus-output-bound-"));
  try {
    const result = path.join(scratch, "result.json"); const stdout = path.join(scratch, "stdout"); const stderr = path.join(scratch, "stderr");
    const run = spawnSync(process.execPath, [helper, "--result", result, "--stdout", stdout, "--stderr", stderr, "--timeout", "5", ...guardArgs, "--", "/bin/sh", "-c", "yes x | head -c 17000000"], { encoding: "utf8", timeout: 10_000 });
    assert.notEqual(run.status, 0);
    const receipt = JSON.parse(readFileSync(result, "utf8"));
    assert.match(receipt.monitor_error, /stdout exceeded 16777216 bytes/);
    assert.ok(readFileSync(stdout).length <= 16 * 1024 * 1024);
    assert.equal(readFileSync(stderr).length, 0);
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test("foreground guard kills a resistant command group within its terminal deadline", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-focus-group-"));
  try {
    const result = path.join(scratch, "result.json"); const stdout = path.join(scratch, "stdout"); const stderr = path.join(scratch, "stderr"); const pidFile = path.join(scratch, "descendant.pid");
    const started = Date.now();
    const script = `trap '' TERM; /bin/sh -c 'trap "" TERM; sleep 30' & echo $! > '${pidFile}'; wait`;
    const run = spawnSync(process.execPath, [helper, "--result", result, "--stdout", stdout, "--stderr", stderr, "--timeout", "1", ...guardArgs, "--", "/bin/sh", "-c", script], { encoding: "utf8", timeout: 5_000 });
    assert.notEqual(run.status, 0);
    assert.ok(Date.now() - started < 4_500);
    const descendant = Number(readFileSync(pidFile, "utf8").trim());
    assert.throws(() => process.kill(descendant, 0));
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test("foreground guard kills a resistant descendant after its leader accepts TERM", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-focus-descendant-"));
  try {
    const result = path.join(scratch, "result.json"); const stdout = path.join(scratch, "stdout"); const stderr = path.join(scratch, "stderr"); const pidFile = path.join(scratch, "descendant.pid");
    const script = `/bin/sh -c 'trap "" TERM; exec >/dev/null 2>&1; sleep 30' & echo $! > '${pidFile}'; wait`;
    const run = spawnSync(process.execPath, [helper, "--result", result, "--stdout", stdout, "--stderr", stderr, "--timeout", "1", ...guardArgs, "--", "/bin/sh", "-c", script], { encoding: "utf8", timeout: 5_000 });
    assert.notEqual(run.status, 0);
    const descendant = Number(readFileSync(pidFile, "utf8").trim());
    assert.throws(() => process.kill(descendant, 0), undefined, "the same-group descendant must be absent before the guard returns");
    assert.equal(JSON.parse(readFileSync(result, "utf8")).monitor_error, "guarded command timed out");
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});
