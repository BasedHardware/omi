import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const helper = path.join(path.dirname(fileURLToPath(import.meta.url)), "macos-foreground-guard.mjs");

test("foreground guard runs a background CLI command without changing focus", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-focus-guard-"));
  try {
    const result = path.join(scratch, "result.json"); const stdout = path.join(scratch, "stdout"); const stderr = path.join(scratch, "stderr");
    const run = spawnSync(process.execPath, [helper, "--result", result, "--stdout", stdout, "--stderr", stderr, "--timeout", "5", "--", "/bin/sh", "-c", "printf guarded"], { encoding: "utf8" });
    assert.equal(run.status, 0, run.stderr);
    const receipt = JSON.parse(readFileSync(result, "utf8"));
    assert.equal(receipt.status, 0);
    assert.equal(receipt.monitor_error, null);
    assert.equal(receipt.interval_milliseconds, 20);
    assert.equal(readFileSync(stdout, "utf8"), "guarded");
    assert.equal(readFileSync(stderr, "utf8"), "");
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test("foreground guard fails closed on timeout and writes a terminal result", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-focus-timeout-"));
  try {
    const result = path.join(scratch, "result.json"); const stdout = path.join(scratch, "stdout"); const stderr = path.join(scratch, "stderr");
    const run = spawnSync(process.execPath, [helper, "--result", result, "--stdout", stdout, "--stderr", stderr, "--timeout", "1", "--", "/bin/sh", "-c", "sleep 5"], { encoding: "utf8", timeout: 5_000 });
    assert.notEqual(run.status, 0);
    const receipt = JSON.parse(readFileSync(result, "utf8"));
    assert.equal(receipt.monitor_error, "guarded command timed out");
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});
