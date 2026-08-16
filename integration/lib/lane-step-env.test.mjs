import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { disposeL3RunDir, laneStepEnvironment } from "./lane-step-env.mjs";

test("codegen receives a scoped core-directory root without changing the declared repo root", () => {
  const callerEnv = {
    OMI_CORE_ROOT: "/declared/core-repository",
    OMI_PLATFORM_ROOT: "/declared/platform-repository",
    UNRELATED: "retained",
  };

  const childEnv = laneStepEnvironment({
    callerEnv,
    stepEnv: { OMI_CORE_ROOT: "/declared/core-repository/frontend" },
  });

  assert.deepEqual(callerEnv, {
    OMI_CORE_ROOT: "/declared/core-repository",
    OMI_PLATFORM_ROOT: "/declared/platform-repository",
    UNRELATED: "retained",
  });
  assert.equal(childEnv.OMI_CORE_ROOT, "/declared/core-repository/frontend");
  assert.equal(childEnv.OMI_PLATFORM_ROOT, callerEnv.OMI_PLATFORM_ROOT);
  assert.equal(childEnv.UNRELATED, "retained");
  assert.notEqual(childEnv, callerEnv);
});

test("unscoped steps preserve the public root and L3 run directories remain additive", () => {
  const callerEnv = { OMI_CORE_ROOT: "/declared/core-repository" };
  const ordinary = laneStepEnvironment({ callerEnv });
  const l3 = laneStepEnvironment({ callerEnv, l3RunDir: "/tmp/exact-l3-run" });

  assert.equal(ordinary.OMI_CORE_ROOT, callerEnv.OMI_CORE_ROOT);
  assert.equal(ordinary.OMI_DEV_STACK_RUNDIR, undefined);
  assert.equal(l3.OMI_CORE_ROOT, callerEnv.OMI_CORE_ROOT);
  assert.equal(l3.OMI_DEV_STACK_RUNDIR, "/tmp/exact-l3-run");
  assert.equal(callerEnv.OMI_DEV_STACK_RUNDIR, undefined);
});

test("RED-PROOF both registered codegen paths carry the scoped child override", () => {
  const source = readFileSync(new URL("../lanes.mjs", import.meta.url), "utf8");

  assert.match(source, /command: "pnpm codegen:check", env: CORE_CODEGEN_ENV/);
  assert.match(source, /command: "pnpm verify", env: CORE_CODEGEN_ENV/);
  assert.match(source, /env: laneStepEnvironment\(\{ callerEnv: process\.env, stepEnv: step\.env, l3RunDir \}\)/);
});

test("RED-PROOF a failed L3 keeps its run dir and a passing one does not", () => {
  // red-proof: restore `if (l3RunDir !== null) rmSync(...)` in lanes.mjs, or
  // call disposeL3RunDir with passed:true on a failed receipt. The failed
  // log vanishes and this assertion fails.
  const failed = mkdtempSync(join(tmpdir(), "omi-l3-failed-"));
  const passed = mkdtempSync(join(tmpdir(), "omi-l3-passed-"));
  try {
    writeFileSync(join(failed, "service.log"), "sanitized iOS 124\n");
    writeFileSync(join(passed, "service.log"), "ok\n");

    assert.equal(disposeL3RunDir(null, { passed: true }), false);
    assert.equal(disposeL3RunDir(failed, { passed: false }), false);
    assert.equal(existsSync(join(failed, "service.log")), true, "failed L3 must leave its log behind");

    assert.equal(disposeL3RunDir(passed, { passed: true }), true);
    assert.equal(existsSync(passed), false, "passing L3 must not leave the run dir");
  } finally {
    rmSync(failed, { recursive: true, force: true });
    rmSync(passed, { recursive: true, force: true });
  }

  const source = readFileSync(new URL("../lanes.mjs", import.meta.url), "utf8");
  assert.match(source, /disposeL3RunDir\(l3RunDir, \{ passed: receipt\.result === "pass" \}\)/);
  assert.doesNotMatch(source, /if \(l3RunDir !== null\) rmSync/);
});
