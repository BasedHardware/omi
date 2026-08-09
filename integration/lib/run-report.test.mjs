// LIFECYCLE: permanent
//
// Red-proofs for the ASSERTION PATH ITSELF.
//
// This file exists because of the seventh failure. Six mechanisms reported
// success for things that had not happened; the seventh was inside the
// acceptance path built to catch the other six. An assertion that has never been
// seen red is not evidence — it is a decoration that happens to be green, and
// the only way to know which one you have is to make it fail on purpose.
//
// So each assertion in ASSERTIONS gets a test that hands buildReport() facts
// engineered to violate exactly that assertion, and requires it to go red. These
// are the CHEAP half of the red-proof: they prove the evaluator can fail.
// `integration/red-proof-assert.sh` is the expensive half — it applies the same
// three failures to the REAL running stack, because an evaluator that can fail
// on doctored input still tells you nothing about whether the launcher feeds it
// honest input.
//
// Run: node --test integration/lib/run-report.test.mjs

import assert from "node:assert/strict";
import { test } from "node:test";

import { buildReport, nextActions } from "./run-report.mjs";
import { workspaceStamps } from "./provenance.mjs";

const CLIENT = "run-test-client";

/** A facts object whose every assertion passes, as the baseline to mutate from. */
function healthyFacts(overrides = {}) {
  const stamps = workspaceStamps();
  const runtimeState = {
    route: "memories",
    selected: { memories: "platform" },
    rejected: [],
    rendered: { surface: "memories-platform", memoriesGeneration: "platform" },
    mismatch: null,
  };
  const acceptanceLog = [
    `PROBE_JS: ${JSON.stringify(JSON.stringify(runtimeState))} error: none`,
    "ACCEPTANCE phase=ready-timeout bridge=enabled dispatched=4 succeeded=4 httpError=0 transportFailure=0 servedCount=4 status=PASS",
  ].join("\n");
  return {
    runId: "run-test",
    startedAt: new Date().toISOString(),
    clientId: CLIENT,
    generation: "platform",
    mode: "run",
    attach: false,
    backendUrl: "http://127.0.0.1:4851",
    // wantSurfaces:false keeps the dist stamp (a real file on disk, which may
    // legitimately be stale while someone is mid-edit) out of the baseline. The
    // stamps_agree test below supplies its own artifact instead, so this suite
    // never depends on whether somebody happened to run a build.
    wantSurfaces: false,
    backendStatsBefore: JSON.stringify({ servedRequests: 0, servedReads: 0 }),
    backendStatsAfter: JSON.stringify({
      servedRequests: 4,
      servedReads: 4,
      servedReadsByClient: { [CLIENT]: 4 },
      rows: 7,
      stamp: { ...stamps.platform, artifact: "backend-process" },
    }),
    macos: {
      port: 5290,
      pid: "12345",
      windowed: true,
      pidAlive: true,
      surfaceAnswers: true,
      launchStatus: 0,
      acceptanceLog,
      buildDir: "/nonexistent-on-purpose",
      appName: "omi-on-integration",
    },
    ios: null,
    ...overrides,
  };
}

function assertionNamed(report, name) {
  const found = report.assertions.find((a) => a.name === name);
  assert.ok(found, `expected assertion ${name} to have been evaluated; got ${report.assertions.map((a) => a.name).join(",")}`);
  return found;
}

test("the healthy baseline passes — otherwise every red below proves nothing", () => {
  const report = buildReport(healthyFacts());
  const failed = report.assertions.filter((a) => a.result === "fail");
  assert.deepEqual(failed.map((a) => `${a.name}: ${a.detail}`), [], "baseline must be green");
  assert.equal(report.result, "pass");
});

test("every assertion names its arbiter, and single-measurement claims say so", () => {
  // red-proof: delete `corroboratedBy` from any row in ASSERTIONS, or set
  // singleMeasurement to a constant false — this test then fails, because the
  // whole point of the field is that a reader can tell which claims rest on one
  // number. Verified red by setting `singleMeasurement: false` unconditionally.
  const report = buildReport(healthyFacts());
  for (const a of report.assertions) {
    assert.ok(a.claim && a.claim.length > 0, `${a.name} has no claim`);
    assert.ok(a.measuredBy && a.measuredBy.length > 0, `${a.name} names no arbiter`);
    assert.equal(a.singleMeasurement, a.corroboratedBy === null, `${a.name} mislabels its corroboration`);
  }
  const single = report.assertions.filter((a) => a.singleMeasurement).map((a) => a.name);
  assert.deepEqual(single, ["backend_reachable"], "only backend_reachable should rest on one measurement");
});

test("RED-PROOF backend_reachable: the backend is gone", () => {
  // red-proof: this is the applied mutation `kill the backend mid-run`. With no
  // parseable /qa/stats body there is no arbiter at all, and a run that cannot
  // measure must never report pass.
  const report = buildReport(healthyFacts({ backendStatsAfter: "" }));
  assert.equal(assertionNamed(report, "backend_reachable").result, "fail");
  assert.equal(report.result, "fail");
});

test("RED-PROOF served_reads_by_this_run: another client produced the traffic", () => {
  // red-proof: THE load-bearing one. The global counter moved 0 -> 4, which the
  // old `before -> after` delta would have accepted as proof. It was somebody
  // else's traffic. Keyed by client id, the claim correctly fails.
  const facts = healthyFacts({
    backendStatsAfter: JSON.stringify({
      servedRequests: 4,
      servedReads: 4,
      servedReadsByClient: { "some-other-agents-stack": 4 },
    }),
  });
  const report = buildReport(facts);
  const a = assertionNamed(report, "served_reads_by_this_run");
  assert.equal(a.result, "fail");
  assert.match(a.detail, /ZERO reads/);
  // The delta is still reported — it is context. It is just no longer evidence.
  assert.equal(report.backend.readsDelta, 4);
});

test("RED-PROOF no_generation_mismatch: the selection was honored and then never used", () => {
  // red-proof: this is the applied mutation `force the legacy branch under a
  // platform selection`. `generation=platform` with no route leaves route=home,
  // which takes the legacy branch — nothing is rejected, the app looks perfect,
  // and it is reading the wrong backend.
  const runtimeState = {
    route: "home",
    selected: { memories: "platform" },
    rejected: [],
    rendered: { surface: "home", memoriesGeneration: "legacy" },
    mismatch: "memories: selected platform, rendered legacy (surface home)",
  };
  const facts = healthyFacts();
  facts.macos.acceptanceLog = `PROBE_JS: ${JSON.stringify(JSON.stringify(runtimeState))} error: none\n${facts.macos.acceptanceLog.split("\n")[1]}`;
  const report = buildReport(facts);
  const a = assertionNamed(report, "no_generation_mismatch");
  assert.equal(a.result, "fail");
  assert.match(a.detail, /honored and then never used/);
});

test("RED-PROOF no_generation_mismatch: nothing was constructed at all", () => {
  // red-proof: `rendered: null` is the state where the surface never got as far
  // as building anything. A check that only compared selected-vs-rendered would
  // read two nulls as agreement and pass.
  const runtimeState = { route: "memories", selected: { memories: "platform" }, rejected: [], rendered: null, mismatch: null };
  const facts = healthyFacts();
  facts.macos.acceptanceLog = `PROBE_JS: ${JSON.stringify(JSON.stringify(runtimeState))} error: none`;
  const report = buildReport(facts);
  assert.equal(assertionNamed(report, "no_generation_mismatch").result, "fail");
});

test("RED-PROOF stamps_agree: the artifact was built from a different tree", () => {
  // red-proof: this is the applied mutation `point at a stale dist`. The stamp
  // is well-formed and internally consistent; it simply describes source that is
  // no longer checked out. This is the single check that subsumes stale dist,
  // wrong shell, wrong branch and edited-but-not-rebuilt.
  const stamps = workspaceStamps();
  const facts = healthyFacts({
    backendStatsAfter: JSON.stringify({
      servedRequests: 4,
      servedReads: 4,
      servedReadsByClient: { [CLIENT]: 4 },
      stamp: { ...stamps.platform, artifact: "backend-process", treeHash: "0".repeat(40) },
    }),
  });
  const report = buildReport(facts);
  const a = assertionNamed(report, "stamps_agree");
  assert.equal(a.result, "fail");
  assert.match(a.detail, /backend-process/);
});

test("RED-PROOF window_alive: the process died right after launch", () => {
  // red-proof: the pkill incident. Every log line was true in isolation and the
  // net result was no app, under a summary reading "window should be open now".
  const facts = healthyFacts();
  facts.macos.pidAlive = false;
  const report = buildReport(facts);
  assert.equal(assertionNamed(report, "window_alive").result, "fail");
});

test("RED-PROOF window_alive: alive but serving nothing", () => {
  // red-proof: a live process with a dead surface is exactly as useless to QA as
  // no process, and only the second measurement can tell them apart.
  const facts = healthyFacts();
  facts.macos.surfaceAnswers = false;
  const report = buildReport(facts);
  assert.equal(assertionNamed(report, "window_alive").result, "fail");
});

test("RED-PROOF: a run that drove nothing is INCONCLUSIVE, never a pass", () => {
  // red-proof: replace the corroboration guard with `report.result = "pass"`,
  // or restore the earlier `assertions.length === 0` form. Both make this test
  // fail. The `length === 0` version is the instructive one: it PASSED this
  // suite while being dead code, because `backend_reachable` always applies and
  // the branch could never be reached. Applying the mutation is what exposed it.
  //
  // This is `--only-backend --assert`: a healthy server, nothing driven at it,
  // and nothing to contradict the one measurement taken.
  const report = buildReport({
    runId: "run-backend-only",
    startedAt: new Date().toISOString(),
    clientId: CLIENT,
    generation: "legacy",
    mode: "run",
    backendUrl: "http://127.0.0.1:4851",
    wantSurfaces: false,
    backendStatsBefore: JSON.stringify({ servedRequests: 0, servedReads: 0 }),
    backendStatsAfter: JSON.stringify({ servedRequests: 0, servedReads: 0 }),
    macos: null,
    ios: null,
  });
  // Deliberately NOT an exact list of assertion names: the earlier version of
  // this test pinned it to ["backend_reachable"] and broke the moment
  // `stamps_agree` legitimately started applying to attach-mode runs. Pinning
  // the incidental set made the test about the registry's contents instead of
  // about the invariant it is named for. Assert the invariant.
  assert.ok(report.assertions.length > 0, "some assertions ran");
  assert.ok(report.assertions.every((a) => a.result === "pass"), "and all of them passed");
  assert.equal(report.assertions.some((a) => ["served_reads_by_this_run", "no_generation_mismatch", "window_alive"].includes(a.name)), false,
    "but none of them is about what an app did");
  assert.equal(report.result, "inconclusive", "…so the run proves nothing");
});

// ── The write journey's row ─────────────────────────────────────────────────
// The journey judges itself; this row decides only whether its verdict is
// allowed to redden L3 tonight. These red-proofs are about THAT decision.

/** A journey verdict of the given shape, as `write-journey.mjs` would write it. */
const journeyVerdict = ({ gating, failing = 0, pending = [] }) => ({
  schema: 1,
  runId: "run-test",
  stage: gating ? "b" : "a",
  door: { url: gating ? "http://127.0.0.1:4851" : "http://127.0.0.1:4853", opsPath: "/v1/tasks/ops" },
  assertions: [
    { name: "create_admitted", result: "pass", detail: "ok" },
    ...Array.from({ length: failing }, (_, i) => ({ name: `broken_${i}`, result: "fail", detail: "the two arbiters disagree" })),
    ...pending.map((name) => ({ name, result: "pending", detail: "the door does not exist yet" })),
  ],
  pending,
  result: failing > 0 ? "fail" : (pending.length > 0 ? "partial" : "pass"),
  gating,
  gatingNote: gating ? null : "stage (a): /v1/tasks/ops has no WIRE_PATH_REGISTRY row",
});

test("a stage-(a) journey with pending steps passes, and says which steps it could not measure", () => {
  const report = buildReport(healthyFacts({
    writeJourney: journeyVerdict({ gating: false, pending: ["server_applied_observation", "idempotent_replay"] }),
  }));
  const a = assertionNamed(report, "write_journey");
  assert.equal(a.result, "pass");
  assert.match(a.detail, /2 PENDING/);
  assert.match(a.detail, /server_applied_observation/);
});

test("RED-PROOF write_journey: a failing journey at a REGISTERED door fails the run", () => {
  // The retirement condition, made mechanical. Once /v1/tasks/ops has a
  // registry row the journey gates like anything else — no edit, no flag,
  // nobody having to remember.
  const report = buildReport(healthyFacts({ writeJourney: journeyVerdict({ gating: true, failing: 1 }) }));
  assert.equal(assertionNamed(report, "write_journey").result, "fail");
  assert.equal(report.result, "fail");
});

test("RED-PROOF write_journey: a failing stage-(a) journey is ADVISORY — never a pass, never silent", () => {
  // The trap this avoids: returning "pass" for a suppressed row. That would
  // convert "we chose not to gate on this" into "we checked", and it would let
  // a broken journey satisfy the behavioural guard below all by itself.
  const report = buildReport(healthyFacts({ writeJourney: journeyVerdict({ gating: false, failing: 2 }) }));
  const a = assertionNamed(report, "write_journey");
  assert.equal(a.result, "advisory");
  assert.match(a.detail, /NOT GATING L3/);
  assert.match(a.detail, /broken_0/, "the failing step names are in the record, not just a count");
  assert.equal(report.result, "pass", "an advisory does not redden six lanes' trunk");
  assert.ok(
    nextActions(report).some((x) => x.includes("was reported and NOT gated")),
    "…and it is not silent either",
  );
});

test("RED-PROOF write_journey: an advisory journey cannot supply the behavioural evidence a run needs", () => {
  // `--only-backend` plus a broken, non-gating journey. Nothing about an app
  // was established, so the run must be INCONCLUSIVE rather than pass.
  const report = buildReport({
    runId: "run-journey-only",
    startedAt: new Date().toISOString(),
    clientId: CLIENT,
    generation: "legacy",
    mode: "run",
    backendUrl: "http://127.0.0.1:4851",
    wantSurfaces: false,
    backendStatsBefore: JSON.stringify({ servedRequests: 0, servedReads: 0 }),
    backendStatsAfter: JSON.stringify({ servedRequests: 0, servedReads: 0 }),
    macos: null,
    ios: null,
    writeJourney: journeyVerdict({ gating: false, failing: 1 }),
  });
  assert.equal(assertionNamed(report, "write_journey").result, "advisory");
  assert.equal(report.result, "inconclusive");
});

test("a green gating journey IS behavioural evidence on its own", () => {
  const report = buildReport({
    runId: "run-journey-only-green",
    startedAt: new Date().toISOString(),
    clientId: CLIENT,
    generation: "legacy",
    mode: "run",
    backendUrl: "http://127.0.0.1:4851",
    wantSurfaces: false,
    backendStatsBefore: JSON.stringify({ servedRequests: 0, servedReads: 0 }),
    backendStatsAfter: JSON.stringify({ servedRequests: 0, servedReads: 0 }),
    macos: null,
    ios: null,
    writeJourney: journeyVerdict({ gating: true }),
  });
  assert.equal(report.result, "pass");
});

test("no journey at all means the row does not apply — and the run cannot borrow its credit", () => {
  const report = buildReport(healthyFacts());
  assert.equal(report.assertions.some((a) => a.name === "write_journey"), false);
  assert.equal(report.writeJourney, null);
});

test("readsByThisRun is null, not 0, when the backend cannot answer the question", () => {
  // red-proof: replace `?? null` with `?? 0` in readsFor(). "The backend does
  // not count per client" and "this run read nothing" are different findings,
  // and collapsing them into 0 would report a working stack as broken — the
  // false RED that trains people to ignore the check.
  const facts = healthyFacts({
    backendStatsAfter: JSON.stringify({ servedRequests: 4, servedReads: 4 }),
  });
  const report = buildReport(facts);
  assert.equal(report.backend.readsByThisRun, null);
});
