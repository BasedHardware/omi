import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { backlogHours, describeCapture } from "../src/production/capture-state.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("ceiling stop is loud and is not idle", () => {
  // red-proof: mapping stopped-at-ceiling to idle copy, or setting loud:false, must fail this
  const described = describeCapture({ kind: "stopped-at-ceiling", untranscribedSeconds: 7200 });
  assert.equal(described.loud, true);
  assert.equal(described.capturing, false);
  assert.equal(described.titleKey, "listen.stateStoppedAtCeiling");
  assert.notEqual(described.titleKey, "listen.stateIdle");
});

test("entitlement pause still reports capture running and reports the backlog", () => {
  // red-proof: treating the entitlement pause as a stop (capturing:false) must fail this
  const described = describeCapture({
    kind: "paused-for-entitlement",
    elapsedSeconds: 600,
    untranscribedSeconds: 10800,
  });
  assert.equal(described.capturing, true);
  assert.equal(described.backlogSeconds, 10800);
  assert.equal(described.titleKey, "listen.statePausedEntitlement");
});

test("offline buffering is distinguishable from capturing and ceiling", () => {
  // red-proof: collapsing offline into plain capturing must fail this
  const described = describeCapture({
    kind: "offline-buffering",
    elapsedSeconds: 900,
    bufferedSeconds: 300,
    untranscribedSeconds: 3600,
  });
  assert.equal(described.capturing, true);
  assert.equal(described.titleKey, "listen.stateOfflineBuffering");
  assert.notEqual(described.titleKey, "listen.stateCapturing");
  assert.notEqual(described.titleKey, "listen.stateStoppedAtCeiling");
});

test("a non-zero backlog never renders as nothing", () => {
  // red-proof: Math.floor(seconds/3600) must fail this
  const hours = backlogHours(60);
  assert.ok(hours > 0);
  assert.equal(hours, 1);
});

test("every capture kind is handled with a distinct non-empty title key", () => {
  // red-proof: omitting a kind's mapping (so describeCapture throws) or
  // returning an empty titleKey must fail this
  const samples = [
    { kind: "idle" },
    { kind: "capturing", elapsedSeconds: 10 },
    { kind: "paused-for-entitlement", elapsedSeconds: 20, untranscribedSeconds: 30 },
    { kind: "offline-buffering", elapsedSeconds: 40, bufferedSeconds: 50, untranscribedSeconds: 60 },
    { kind: "stopped-at-ceiling", untranscribedSeconds: 70 },
    { kind: "error", retryable: false },
  ];
  const titleKeys = samples.map((sample) => {
    const described = describeCapture(sample);
    assert.equal(typeof described.titleKey, "string");
    assert.notEqual(described.titleKey, "");
    return described.titleKey;
  });
  assert.equal(new Set(titleKeys).size, titleKeys.length);
});

test("ListenProduction announces loud states and has no pause control", async () => {
  const source = await read("src/production/ListenProduction.tsx");
  assert.match(source, /role=\{description\.loud \? "alert" : "status"\}/);
  assert.doesNotMatch(source, /store\.pause|listen\.pause|"pause"/i);
  // red-proof (supplement): removing the loud alert branch or adding a pause
  // control would fail this source guard.
});
