import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { laneStepEnvironment } from "./lane-step-env.mjs";

test("codegen receives a scoped core-directory root without changing the declared repo root", () => {
  const callerEnv = {
    OMI_CORE_ROOT: "/declared/core-repository",
    OMI_PLATFORM_ROOT: "/declared/platform-repository",
    UNRELATED: "retained",
  };

  const childEnv = laneStepEnvironment({
    callerEnv,
    stepEnv: { OMI_CORE_ROOT: "/declared/core-repository/core" },
  });

  assert.deepEqual(callerEnv, {
    OMI_CORE_ROOT: "/declared/core-repository",
    OMI_PLATFORM_ROOT: "/declared/platform-repository",
    UNRELATED: "retained",
  });
  assert.equal(childEnv.OMI_CORE_ROOT, "/declared/core-repository/core");
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
