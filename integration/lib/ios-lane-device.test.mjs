import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, test } from "node:test";

import { appendDeviceArgument, holdSimulatorLease, isIosStackAssertCommand } from "./ios-lane-device.mjs";

const scratchDirs = [];
afterEach(() => {
  for (const dir of scratchDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function scratch() {
  const dir = mkdtempSync(join(tmpdir(), "omi-ios-lane-device-"));
  scratchDirs.push(dir);
  return dir;
}

const UDID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1";

test("L3 assert command gets --device; control-acceptance does not", () => {
  const assertCmd = "integration/dev-stack.sh --assert --lease";
  assert.equal(isIosStackAssertCommand(assertCmd), true);
  assert.equal(
    appendDeviceArgument(assertCmd, UDID),
    "integration/dev-stack.sh --assert --lease --device aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
  );
  assert.equal(
    appendDeviceArgument("node integration/control-acceptance/run.mjs", UDID),
    "node integration/control-acceptance/run.mjs",
  );
  assert.equal(appendDeviceArgument(assertCmd, UDID), appendDeviceArgument(appendDeviceArgument(assertCmd, UDID), UDID));
});

test("RED-PROOF a non-UDID device value is refused rather than interpolated", () => {
  assert.throws(
    () => appendDeviceArgument("integration/dev-stack.sh --assert --lease", "first-booted"),
    /non-UDID/,
  );
});

test("holdSimulatorLease returns the written UDID and SIGTERMs the holder", () => {
  const dir = scratch();
  const holder = join(dir, "holder.ts");
  const outPath = join(dir, "lease.json");
  writeFileSync(holder, `
    const out = process.argv[process.argv.indexOf("--out") + 1];
    await Bun.write(out, JSON.stringify({
      schema: "omi.stack-simulator-lease.v1",
      udid: ${JSON.stringify(UDID)},
      name: "iPhone 17",
    }) + "\\n");
    await new Promise(() => {});
  `);
  const held = holdSimulatorLease({
    holderScript: holder,
    runId: "run-hold",
    outPath,
    parentPid: process.pid,
    readyTimeoutMs: 5_000,
  });
  try {
    assert.equal(held.udid, UDID);
    assert.equal(held.name, "iPhone 17");
  } finally {
    held.release();
  }
});

test("RED-PROOF a holder refusal is the error, not a timeout", () => {
  const dir = scratch();
  const holder = join(dir, "holder.ts");
  const outPath = join(dir, "lease.json");
  const refusal =
    "ERROR: could not acquire a run-scoped iOS simulator (max 4 concurrent);"
    + " all candidates are leased or are devices this harness did not boot."
    + " live leases: iPhone 17 (bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2) pid=12345 runId=run-held-b"
    + " This is a refusal, not a fallback.";
  writeFileSync(holder, `
    process.stderr.write(${JSON.stringify(refusal)} + "\\n");
    process.exit(1);
  `);
  let thrown;
  try {
    holdSimulatorLease({
      holderScript: holder,
      runId: "run-refuse",
      outPath,
      parentPid: process.pid,
      readyTimeoutMs: 5_000,
    });
  } catch (error) {
    thrown = error;
  }
  assert.ok(thrown instanceof Error);
  assert.equal(thrown.message, refusal);
  assert.doesNotMatch(thrown.message, /\b124\b/);
});

test("lanes.mjs still registers the static L3 command and appends --device at execution", () => {
  const result = spawnSync("node", ["--input-type=module", "-e", `
    import { readFileSync } from "node:fs";
    import { appendDeviceArgument } from ${JSON.stringify(new URL("./ios-lane-device.mjs", import.meta.url).pathname)};
    const source = readFileSync(${JSON.stringify(new URL("../lanes.mjs", import.meta.url).pathname)}, "utf8");
    if (!source.includes('command: "integration/dev-stack.sh --assert --lease"')) process.exit(2);
    if (!source.includes("appendDeviceArgument(step.command, simulatorLease?.udid)")) process.exit(3);
    const command = appendDeviceArgument("integration/dev-stack.sh --assert --lease", ${JSON.stringify(UDID)});
    process.stdout.write(command);
  `], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, `integration/dev-stack.sh --assert --lease --device ${UDID}`);
});
