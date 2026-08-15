import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import {
  HOME_FAILURE_NOTICE,
  PASS_VERDICTS,
  PENDING_VALUE,
  SCHEMA,
  STEP_SLUGS,
  aggregate,
  formatControlLine,
  inspectListenChannel,
  inspectScreenChannel,
  isPass,
  isSkip,
  parseProbeJsLine,
  reportFromProbeText,
} from "./verdict.mjs";
import { buildDriverSource } from "./driver-source.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const driver = readFileSync(join(here, "driver.js"), "utf8");
const run = readFileSync(join(here, "run.mjs"), "utf8");
const lanes = readFileSync(join(here, "../lanes.mjs"), "utf8");

const passingSteps = () => STEP_SLUGS.map((slug) => ({
  slug,
  verdict: PASS_VERDICTS[slug][0],
}));

test("slug inventory is frozen and every slug has a pass token", () => {
  // red-proof: rename `mic` to `listen` or drop `screen` from STEP_SLUGS.
  assert.deepEqual([...STEP_SLUGS], [
    "home",
    "chat",
    "mic",
    "screen",
    "nav.home",
    "nav.conversations",
    "nav.memories",
    "nav.folders",
    "nav.tasks",
    "nav.rewind",
    "nav.apps",
    "nav.brain-map",
    "nav.chat",
    "nav.settings",
    "nav.listen",
  ]);
  for (const slug of STEP_SLUGS) {
    assert.ok(PASS_VERDICTS[slug]?.length > 0, slug);
    assert.equal(formatControlLine(slug, PASS_VERDICTS[slug][0]), `CONTROL ${slug}=${PASS_VERDICTS[slug][0]}`);
  }
});

test("RED-PROOF a missing omiScreenBridge is bridge-unreachable, never a pass", () => {
  // red-proof: return "present" when the handler is absent.
  assert.equal(inspectScreenChannel({}), "bridge-unreachable");
  assert.equal(inspectScreenChannel({ webkit: { messageHandlers: {} } }), "bridge-unreachable");
  assert.equal(inspectScreenChannel({ webkit: { messageHandlers: { omiScreenBridge: {} } } }), "bridge-unreachable");
  const reachable = inspectScreenChannel({
    webkit: { messageHandlers: { omiScreenBridge: { postMessage() {} } } },
  });
  assert.equal(reachable, "present");
  const verdict = aggregate([{ slug: "screen", verdict: "bridge-unreachable" }]);
  assert.equal(verdict.status, "FAIL");
  assert.equal(verdict.passed, 0);
  assert.equal(verdict.failed, STEP_SLUGS.length);
  assert.ok(verdict.lines.includes("CONTROL screen=bridge-unreachable"));
  assert.equal(isPass("screen", "bridge-unreachable"), false);
});

test("a present screen channel with reached-os is a pass for that slug only", () => {
  const steps = passingSteps();
  const verdict = aggregate(steps);
  assert.equal(verdict.status, "PASS");
  assert.equal(verdict.passed, STEP_SLUGS.length);
  assert.equal(verdict.failed, 0);
  assert.equal(verdict.skipped, 0);
  assert.equal(verdict.skipList, "CONTROL-ACCEPTANCE skips: (none)");
});

test("RED-PROOF a skip is printed and is not counted as a pass", () => {
  // red-proof: treat skipped-tcc-denied as passed, or omit it from the skip list.
  const steps = passingSteps().map((step) => (
    step.slug === "mic" ? { slug: "mic", verdict: "skipped-tcc-denied" } : step
  ));
  const verdict = aggregate(steps);
  assert.equal(isSkip("skipped-tcc-denied"), true);
  assert.equal(isPass("mic", "skipped-tcc-denied"), false);
  assert.equal(verdict.status, "PASS");
  assert.equal(verdict.passed, STEP_SLUGS.length - 1);
  assert.equal(verdict.skipped, 1);
  assert.equal(verdict.failed, 0);
  assert.match(verdict.skipList, /mic=skipped-tcc-denied/);
  assert.doesNotMatch(verdict.summary, /passed=15/);
});

test("overall FAIL when any step is neither pass nor skip, including a missing step", () => {
  const verdict = aggregate([
    { slug: "home", verdict: "ready" },
    { slug: "screen", verdict: "bridge-unreachable" },
  ]);
  assert.equal(verdict.status, "FAIL");
  assert.ok(verdict.failed >= 2);
  assert.ok(verdict.lines.includes("CONTROL chat=missing-step"));
  assert.ok(verdict.failures.includes("CONTROL screen=bridge-unreachable"));
});

test("skipped-already-granted does not make a red control look green", () => {
  const steps = passingSteps().map((step) => (
    step.slug === "screen" ? { slug: "screen", verdict: "skipped-already-granted" } : step
  ));
  const verdict = aggregate(steps);
  assert.equal(verdict.status, "PASS");
  assert.equal(verdict.skipped, 1);
  assert.equal(isPass("screen", "skipped-already-granted"), false);
});

test("listen channel inspection matches the socket the mic control posts to", () => {
  assert.equal(inspectListenChannel({}), "channel-unreachable");
  assert.equal(
    inspectListenChannel({ webkit: { messageHandlers: { omiListenSocket: { postMessage() {} } } } }),
    "present",
  );
});

test("PROBE_JS parser reads the last probe line and rejects a pending timeout", () => {
  const payload = JSON.stringify({ schema: SCHEMA, steps: [{ slug: "screen", verdict: "bridge-unreachable" }] });
  const text = [
    "launched: app",
    `PROBE_JS: ${PENDING_VALUE} error: none`,
    `PROBE_JS: ${payload} error: none`,
  ].join("\n");
  const parsed = parseProbeJsLine(text);
  assert.equal(parsed.ok, true);
  assert.equal(parsed.result.steps[0].verdict, "bridge-unreachable");

  const timedOut = parseProbeJsLine(`PROBE_JS: ${PENDING_VALUE} error: none\n`);
  assert.equal(timedOut.ok, false);
  assert.equal(timedOut.reason, "probe-timeout");
  const report = reportFromProbeText(`PROBE_JS: ${PENDING_VALUE} error: none\n`);
  assert.equal(report.status, "FAIL");
  assert.ok(report.lines.includes("CONTROL harness=probe-timeout"));
});

test("the in-page driver clicks surface controls and does not call stores", () => {
  // red-proof: replace button.click() with store.startCapture() and call that a control test.
  assert.match(driver, /button\.click\(\)|el\.click\(\)/);
  assert.match(driver, /data-consumer-action='start-listen'/);
  assert.match(driver, /button\.screen-capture-toggle/);
  assert.match(driver, /button\.chat-send/);
  assert.match(driver, /Allow microphone/);
  assert.match(driver, /omiScreenBridge/);
  assert.match(driver, /__omiCAMode/);
  assert.match(driver, /HOME_FAILURE_NOTICE/);
  assert.match(driver, /permission === "checking"/);
  assert.doesNotMatch(driver, /store\.startCapture\(|store\.requestPermission\(/);
  assert.equal(driver.includes(HOME_FAILURE_NOTICE), true);
});

test("skipped-not-requested is a skip, and a dead screen still fails the run", () => {
  const steps = STEP_SLUGS.map((slug) => {
    if (slug === "screen") return { slug, verdict: "bridge-unreachable" };
    if (slug === "nav.rewind") return { slug, verdict: "rendered" };
    return { slug, verdict: "skipped-not-requested" };
  });
  const verdict = aggregate(steps);
  assert.equal(verdict.status, "FAIL");
  assert.equal(verdict.passed, 1);
  assert.equal(verdict.skipped, STEP_SLUGS.length - 2);
  assert.ok(verdict.lines.includes("CONTROL screen=bridge-unreachable"));
  assert.match(verdict.skipList, /home=skipped-not-requested/);
});

test("the runner is a sibling of --accept and never aims at production", () => {
  assert.match(run, /dev-run-macos\.sh/);
  assert.match(run, /OMI_PROBE_JS/);
  assert.doesNotMatch(run, /OMI_ACCEPTANCE=1/);
  assert.match(run, /refusing a production origin/);
  assert.match(run, /observed a production origin or \?rig=dev/);
  assert.doesNotMatch(run, /--route[^\n]*rig=dev/);
  assert.match(run, /--screen-proof/);
  assert.match(run, /Does not send Chat/);
  assert.match(run, /real-model proxy is bound on 8791/);
});

test("the driver reaches WKWebView as parseable JavaScript", () => {
  for (const screenProof of [false, true]) {
    const sent = buildDriverSource(driver, { screenProof });
    assert.doesNotThrow(
      () => new Function(sent),
      `driver does not parse with screenProof=${screenProof}`,
    );
  }
});

test("the driver is sent with its newlines, so a line comment ends at its line", () => {
  // Shaped like driver.js: a comment inside the IIFE the probe evaluates.
  const sent = buildDriverSource('(function () {\n// swallow\nreturn 1;\n})()', {});
  assert.match(sent, /\n/);
  assert.doesNotThrow(() => new Function(sent));
  // The shape this replaced: flattening made the comment eat the program.
  assert.throws(() => new Function(sent.replace(/\s+/g, " ")));
});

test("L3 keeps --assert, and states why the control harness is not yet a step", () => {
  assert.match(lanes, /integration\/dev-stack\.sh --assert/);
  assert.match(lanes, /node integration\/control-acceptance\/run\.mjs/);
  // Held out, not softened: if it is ever wired in as an executable step, that
  // must be a deliberate edit, and the note explaining the hold must go with it.
  const l3 = lanes.slice(lanes.indexOf("  L3: {"));
  const stepCommands = [...l3.matchAll(/^\s*command: "(.+)",$/gm)].map((m) => m[1]);
  const holdNoted = /NOT YET A GATE/.test(l3) && /CONTROL home=failure-notice/.test(l3);
  const wiredIn = stepCommands.some((c) => c.includes("control-acceptance/run.mjs"));
  assert.equal(
    wiredIn,
    !holdNoted,
    "control-acceptance is either a real L3 step or an explained hold — never a silent absence",
  );
});
