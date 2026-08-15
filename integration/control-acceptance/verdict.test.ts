import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import {
  CANNED_CHAT_ANSWER,
  CANNED_CHAT_LABEL,
  CANNED_GATEWAY_KIND,
  HOME_FAILURE_NOTICE,
  PASS_VERDICTS,
  PENDING_VALUE,
  REAL_GATEWAY_KIND,
  SCHEMA,
  SKIP_VERDICTS,
  STEP_SLUGS,
  aggregate,
  applyChatProvenance,
  formatControlLine,
  inspectChatProvenance,
  inspectListenChannel,
  inspectListenTranscript,
  inspectScreenChannel,
  inspectScreenFrame,
  isPass,
  isSkip,
  parseProbeJsLine,
  readServiceBoot,
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
  assert.deepEqual([...SKIP_VERDICTS], ["skipped-tcc-denied", "skipped-not-requested"]);
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

test("plumbing verbs are not pass tokens; outcome verbs are", () => {
  // red-proof: put reached-os back in PASS_VERDICTS.mic or PASS_VERDICTS.screen.
  assert.deepEqual([...PASS_VERDICTS.mic], ["transcript-rendered"]);
  assert.deepEqual([...PASS_VERDICTS.screen], ["frame-rendered"]);
  assert.deepEqual([...PASS_VERDICTS.chat], ["streamed-and-persisted"]);
  assert.equal(isPass("mic", "reached-os"), false);
  assert.equal(isPass("screen", "reached-os"), false);
  assert.equal(isPass("mic", "transcript-rendered"), true);
  assert.equal(isPass("screen", "frame-rendered"), true);
});

test("a present screen channel with frame-rendered is a pass for that slug only", () => {
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
  // red-proof: prefix-match skipped-* so this unknown skip counts as a pass.
  const steps = passingSteps().map((step) => (
    step.slug === "screen" ? { slug: "screen", verdict: "skipped-already-granted" } : step
  ));
  const verdict = aggregate(steps);
  assert.equal(isSkip("skipped-already-granted"), false);
  assert.equal(isPass("screen", "skipped-already-granted"), false);
  assert.equal(verdict.status, "FAIL");
  assert.equal(verdict.skipped, 0);
  assert.ok(verdict.failures.includes("CONTROL screen=skipped-already-granted"));
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
  assert.match(driver, /transcript-rendered/);
  assert.match(driver, /data-consumer-transcript/);
  assert.match(driver, /listen-transcript-row/);
  assert.match(driver, /frame-rendered/);
  assert.match(driver, /screen-frame-image/);
  assert.match(driver, /screen-frame-unavailable/);
  assert.match(driver, /data:image\/png;base64,/);
  assert.match(driver, /naturalWidth/);
  assert.match(driver, /chat-agent-capability/);
  assert.match(driver, /skipped-tcc-denied/);
  assert.match(driver, /listen-wait-transcript/);
  assert.match(driver, /timeout\(state, "mic", listenTranscript\(root\)\)/);
  assert.match(driver, /timeout\(state, "screen", screenFrame\(root\)\)/);
  assert.match(driver, /OUTCOME_TICK_LIMIT = 40/);
  assert.match(driver, /root\?\.querySelectorAll\("\.listen-transcript-row"\)/);
  assert.match(driver, /screen-wait-outcome/);
  assert.doesNotMatch(driver, /skipped-already-granted/);
  assert.doesNotMatch(driver, /record\(state, "mic", "reached-os"\)/);
  assert.doesNotMatch(driver, /record\(state, "screen", "reached-os"\)/);
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
  assert.match(run, /OMI_PROBE_MAX_ATTEMPTS: "100"/);
  assert.doesNotMatch(run, /OMI_PROBE_MAX_ATTEMPTS: "150"/);
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
  assert.match(l3, /no platform conversations adapter/);
});

function listenRoot({ semantic, transcript, rows }) {
  return {
    getAttribute(name) {
      if (name === "data-consumer-semantic") return semantic;
      if (name === "data-consumer-transcript") return transcript;
      return null;
    },
    querySelectorAll(selector) {
      if (!String(selector).includes("listen-transcript-row")) return [];
      return rows;
    },
  };
}

function row(text) {
  return {
    textContent: text,
    querySelector(selector) {
      if (selector === ".listen-transcript-text") return { textContent: text };
      return null;
    },
  };
}

test("RED-PROOF mic empty transcript is not transcript-rendered", () => {
  // Stub the transcript source: capturing, zero segments, no rows.
  const empty = inspectListenTranscript(listenRoot({
    semantic: "listen:capture:capturing:segments:0",
    transcript: "",
    rows: [],
  }));
  assert.equal(empty, "empty-transcript");
  assert.equal(isPass("mic", empty), false);
  assert.equal(formatControlLine("mic", empty), "CONTROL mic=empty-transcript");
  const red = aggregate(passingSteps().map((step) => (
    step.slug === "mic" ? { slug: "mic", verdict: empty } : step
  )));
  assert.equal(red.status, "FAIL");
  assert.ok(red.failures.includes("CONTROL mic=empty-transcript"));

  const rendered = inspectListenTranscript(listenRoot({
    semantic: "listen:capture:capturing:segments:2",
    transcript: "Local transcription is connected.",
    rows: [row("Local transcription is connected."), row("This segment arrived with real timing.")],
  }));
  assert.equal(rendered, "transcript-rendered");
  assert.equal(isPass("mic", rendered), true);
  assert.equal(formatControlLine("mic", rendered), "CONTROL mic=transcript-rendered");
  const green = aggregate(passingSteps().map((step) => (
    step.slug === "mic" ? { slug: "mic", verdict: rendered } : step
  )));
  assert.equal(green.status, "PASS");
});

test("RED-PROOF a published segment count without visible rows is not a pass", () => {
  // The helper-vs-JSX miss: attributes set, transcript rows not drawn.
  const ghost = inspectListenTranscript(listenRoot({
    semantic: "listen:capture:capturing:segments:1",
    transcript: "Local transcription is connected.",
    rows: [],
  }));
  assert.equal(ghost, "empty-transcript");
  assert.equal(isPass("mic", ghost), false);
});

test("RED-PROOF screen unavailable paragraph is not frame-rendered", () => {
  const unavailable = inspectScreenFrame({
    querySelector(selector) {
      if (selector === ".screen-frame-unavailable") return { textContent: "Frame image is not available here." };
      return null;
    },
  });
  assert.equal(unavailable, "frame-unavailable");
  assert.equal(isPass("screen", unavailable), false);
  assert.equal(formatControlLine("screen", unavailable), "CONTROL screen=frame-unavailable");
  const red = aggregate(passingSteps().map((step) => (
    step.slug === "screen" ? { slug: "screen", verdict: unavailable } : step
  )));
  assert.equal(red.status, "FAIL");
  assert.ok(red.failures.includes("CONTROL screen=frame-unavailable"));

  const missingBytes = inspectScreenFrame({
    querySelector(selector) {
      if (selector === ".screen-frame-unavailable") return null;
      if (selector === "img.screen-frame-image") {
        return {
          getAttribute(name) { return name === "src" ? "data:image/png;base64," : null; },
          src: "data:image/png;base64,",
          naturalWidth: 0,
        };
      }
      return null;
    },
  });
  assert.equal(missingBytes, "frame-empty-bytes");
  assert.equal(isPass("screen", missingBytes), false);

  const loading = inspectScreenFrame({
    querySelector(selector) {
      if (selector === ".screen-frame-loading") return { textContent: "Loading" };
      return null;
    },
  });
  assert.equal(loading, "frame-loading");
  assert.equal(isPass("screen", loading), false);

  const decoded = inspectScreenFrame({
    querySelector(selector) {
      if (selector === ".screen-frame-unavailable") return null;
      if (selector === "img.screen-frame-image") {
        return {
          getAttribute(name) { return name === "src" ? "data:image/png;base64,iVBORw0KGgo=" : null; },
          src: "data:image/png;base64,iVBORw0KGgo=",
          naturalWidth: 1280,
        };
      }
      return null;
    },
  });
  assert.equal(decoded, "frame-rendered");
  assert.equal(isPass("screen", decoded), true);
  assert.equal(formatControlLine("screen", decoded), "CONTROL screen=frame-rendered");
  const green = aggregate(passingSteps().map((step) => (
    step.slug === "screen" ? { slug: "screen", verdict: decoded } : step
  )));
  assert.equal(green.status, "PASS");
});

test("RED-PROOF canned gateway while declaring real is not streamed-and-persisted", () => {
  // Two witnesses agree canned; intent says real. That is the stub-for-a-week shape.
  const mismatch = inspectChatProvenance({
    intent: "real",
    boot: { event: "service.boot", gateway_kind: CANNED_GATEWAY_KIND },
    label: CANNED_CHAT_LABEL,
    assistantText: CANNED_CHAT_ANSWER,
  });
  assert.equal(mismatch, "provenance-mismatch");
  assert.equal(isPass("chat", mismatch), false);
  assert.equal(formatControlLine("chat", mismatch), "CONTROL chat=provenance-mismatch");
  const rewritten = applyChatProvenance(
    passingSteps(),
    {
      intent: "real",
      boot: { gateway_kind: CANNED_GATEWAY_KIND },
      rendered: { capabilityLabel: CANNED_CHAT_LABEL, assistantText: CANNED_CHAT_ANSWER },
    },
  );
  const red = aggregate(rewritten);
  assert.equal(red.status, "FAIL");
  assert.ok(red.failures.includes("CONTROL chat=provenance-mismatch"));
  assert.equal(rewritten.find((step) => step.slug === "chat")?.verdict, "provenance-mismatch");

  const cannedAgree = inspectChatProvenance({
    intent: "test",
    boot: { event: "service.boot", gateway_kind: CANNED_GATEWAY_KIND },
    label: CANNED_CHAT_LABEL,
    assistantText: CANNED_CHAT_ANSWER,
  });
  assert.equal(cannedAgree, "agree");
  const cannedSteps = applyChatProvenance(passingSteps(), {
    intent: "test",
    boot: { gateway_kind: CANNED_GATEWAY_KIND },
    rendered: { capabilityLabel: CANNED_CHAT_LABEL, assistantText: CANNED_CHAT_ANSWER },
  });
  assert.equal(cannedSteps.find((step) => step.slug === "chat")?.verdict, "streamed-and-persisted");
  assert.equal(aggregate(cannedSteps).status, "PASS");

  const realAgree = inspectChatProvenance({
    intent: "real",
    boot: { event: "service.boot", gateway_kind: REAL_GATEWAY_KIND, gateway_model: "glm-4.7" },
    label: "External model response (glm-4.7)",
    assistantText: "Not the canned gateway string.",
  });
  assert.equal(realAgree, "agree");
  const realCannedText = inspectChatProvenance({
    intent: "real",
    boot: { gateway_kind: REAL_GATEWAY_KIND, gateway_model: "glm-4.7" },
    label: "External model response (glm-4.7)",
    assistantText: CANNED_CHAT_ANSWER,
  });
  assert.equal(realCannedText, "canned-answer");
  assert.equal(isPass("chat", realCannedText), false);
});

test("chat provenance fails when any one of the three witnesses is missing", () => {
  const labelAndBoot = inspectChatProvenance({
    intent: "real",
    boot: { gateway_kind: CANNED_GATEWAY_KIND },
    label: CANNED_CHAT_LABEL,
    assistantText: CANNED_CHAT_ANSWER,
  });
  assert.equal(labelAndBoot, "provenance-mismatch");

  const intentAndBoot = inspectChatProvenance({
    intent: "test",
    boot: { gateway_kind: CANNED_GATEWAY_KIND },
    label: "External model response (glm-4.7)",
    assistantText: CANNED_CHAT_ANSWER,
  });
  assert.equal(intentAndBoot, "provenance-mismatch");

  const intentAndLabel = inspectChatProvenance({
    intent: "test",
    boot: { gateway_kind: REAL_GATEWAY_KIND, gateway_model: "glm-4.7" },
    label: CANNED_CHAT_LABEL,
    assistantText: CANNED_CHAT_ANSWER,
  });
  assert.equal(intentAndLabel, "provenance-mismatch");

  const noBoot = inspectChatProvenance({
    intent: "test",
    boot: null,
    label: CANNED_CHAT_LABEL,
    assistantText: CANNED_CHAT_ANSWER,
  });
  assert.equal(noBoot, "boot-missing");
  assert.equal(isPass("chat", "boot-missing"), false);

  const skipped = applyChatProvenance(
    passingSteps().map((step) => (
      step.slug === "chat" ? { slug: "chat", verdict: "skipped-not-requested" } : step
    )),
    { intent: "real", boot: null, rendered: null },
  );
  assert.equal(skipped.find((step) => step.slug === "chat")?.verdict, "skipped-not-requested");
});

test("readServiceBoot takes the last service.boot event from JSONL", () => {
  const text = [
    JSON.stringify({ ts: "2026-08-15T00:00:00.000Z", proc: "service", event: "dev-stack.start" }),
    JSON.stringify({ ts: "2026-08-15T00:00:01.000Z", proc: "service", event: "service.boot", gateway_kind: CANNED_GATEWAY_KIND }),
    JSON.stringify({ ts: "2026-08-15T00:00:02.000Z", proc: "service", event: "service.ready" }),
    "not-json",
    JSON.stringify({ ts: "2026-08-15T00:00:03.000Z", proc: "service", event: "service.boot", gateway_kind: REAL_GATEWAY_KIND, gateway_model: "glm-4.7" }),
  ].join("\n");
  assert.deepEqual(readServiceBoot(text), {
    ts: "2026-08-15T00:00:03.000Z",
    proc: "service",
    event: "service.boot",
    gateway_kind: REAL_GATEWAY_KIND,
    gateway_model: "glm-4.7",
  });
  assert.equal(readServiceBoot(""), null);
});

test("the runner applies chat provenance from the boot JSONL", () => {
  assert.match(run, /applyChatProvenance/);
  assert.match(run, /readServiceBoot/);
  assert.match(run, /service\.jsonl/);
  assert.match(run, /witnesses\?\.chat/);
});

test("PROBE_JS payload keeps chat witnesses for the provenance clause", () => {
  const payload = JSON.stringify({
    schema: SCHEMA,
    steps: [{ slug: "chat", verdict: "streamed-and-persisted" }],
    witnesses: { chat: { capabilityLabel: CANNED_CHAT_LABEL, assistantText: CANNED_CHAT_ANSWER } },
  });
  const parsed = parseProbeJsLine(`PROBE_JS: ${payload} error: none\n`);
  assert.equal(parsed.ok, true);
  assert.deepEqual(parsed.result.witnesses.chat, {
    capabilityLabel: CANNED_CHAT_LABEL,
    assistantText: CANNED_CHAT_ANSWER,
  });
});
