// LIFECYCLE: permanent
//
// RED-PROOFS FOR THE WRITE JOURNEY'S VERDICT PATH.
//
// `run-report.test.mjs` exists because the seventh failure of that night was
// inside the acceptance path built to catch the other six. This file exists for
// the same reason, one layer further in: the write journey is the artifact that
// will be cited as "the write path works end to end", so its verdict logic is
// the single most attractive place in this repository for a decoration that
// happens to be green.
//
// Every assertion in JOURNEY_ASSERTIONS gets a mutation engineered to violate
// exactly that assertion, and is required to go red. These are the CHEAP half:
// they prove the evaluator CAN fail. The expensive half is applying the same
// mutations to the real running door — `integration/red-proof-write-journey.sh`.
// An evaluator that fails on doctored facts still says nothing about whether
// the driver feeds it honest facts.
//
// The corpus and the classifier here are the REAL ones — platform's vendored
// write-ops-outcomes.json and the shipped `classifyWriteOpsResponse` from the
// built adapter dist. A re-typed copy of either would agree with itself no
// matter what the server sent, which is the cross-side defect in miniature.
//
// Run: node --test integration/lib/write-journey.test.mjs

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { test } from "node:test";

import { judgeOutbox } from "./write-journey-outbox.mjs";
import {
  JOURNEY_ASSERTIONS,
  classifyDoor,
  gatingOf,
  judgeJourney,
  mintWriteId,
  readVendoredWriteOutcomes,
} from "./write-journey.mjs";
import { createReadableTaskBag } from "./write-journey-task.mjs";
import { REPO_PATHS } from "./provenance.mjs";

const corpus = readVendoredWriteOutcomes();
const { classifyWriteOpsResponse: classify } = await import(
  new URL("../../core/packages/adapters-platform/dist/index.js", import.meta.url).href
);
const judge = (journey) => judgeJourney(journey, { corpus, classify });
const outcome = (journey, name) => judge(journey).assertions.find((a) => a.name === name);

const STALE_BODY = corpus.byOutcome.get("stale_epoch").body;
const RUN = "journey-unit";
const WRITE_ID = "a".repeat(64);
const REVISION = "219a4807d8970548f0af5a687bb16d444d7090c74e203b37e072baae95a5f022";

test("the journey writes every bag-backed field in the signed task vocabulary", () => {
  // red-proof: rename `description` back to `title`, `completed` back to
  // `done`, or omit any projection field and this exact-key assertion fails.
  const bag = createReadableTaskBag({
    description: "pick up oat milk",
    completed: false,
  });
  assert.deepEqual(Object.keys(bag), [
    "description",
    "completed",
    "completedAt",
    "dueAt",
    "owner",
    "source",
    "provenance",
    "sortOrder",
    "indentLevel",
    "createdAt",
    "updatedAt",
  ]);
  assert.equal(bag.description, "pick up oat milk");
  assert.equal(bag.completed, false);
  assert.equal("title" in bag, false);
  assert.equal("done" in bag, false);
  assert.equal("id" in bag, false, "id is derived from the envelope record_id");
  assert.equal("revision" in bag, false, "revision is owned by the store hash chain");
});

test("the launcher binds one registered composition for memories, task ops, and task reads", async (t) => {
  // red-proof: replace the launcher import of `createLocalService` with the old
  // memories-only integration server and /v1/tasks/ops returns the unknown-route
  // 404 before this test can create or read the task.
  const launcher = new URL("./write-journey-door.mjs", import.meta.url);
  const child = spawn("bun", [
    launcher.pathname,
    "--platform-repo", REPO_PATHS.platform,
    "--port", "0",
    "--seed", "1",
  ], { stdio: ["ignore", "pipe", "pipe"] });
  t.after(() => {
    if (child.exitCode === null) child.kill("SIGTERM");
  });

  const listening = await new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => reject(new Error(`registered door did not announce itself: ${stderr}`)), 10_000);
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
      const line = stdout.split("\n").find((candidate) => candidate.includes("registered_door_listening"));
      if (line === undefined) return;
      clearTimeout(timeout);
      resolve(JSON.parse(line));
    });
    child.once("error", (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.once("exit", (code) => {
      if (code === 0) return;
      clearTimeout(timeout);
      reject(new Error(`registered door exited ${code}: ${stderr}`));
    });
  });

  const auth = { authorization: `Bearer ${listening.devToken}` };
  assert.equal(Number.isSafeInteger(listening.pid), true, "the listener must announce the PID shutdown owns");
  const control = async (path, body) => {
    const response = await fetch(`${listening.url}${path}`, {
      method: "POST",
      headers: { ...auth, "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    assert.equal(response.status, 200, `${path}: ${await response.text()}`);
  };
  const observation = (overrides) => ({
    account_id: listening.ownerAccountId,
    control_revision: 1,
    account_generation: "legacy",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
    ...overrides,
  });
  await control("/v1/qa/control/reset", {});
  await control("/v1/qa/control/observe", observation({}));
  await control("/v1/qa/control/observe", observation({ control_revision: 2, account_generation: "migrating" }));
  await control("/v1/qa/control/observe", observation({ control_revision: 3, account_generation: "new", account_epoch: 7 }));
  await control("/v1/qa/control/activate", { epoch: 7, at_control_revision: 3 });

  const created = await fetch(`${listening.url}/v1/tasks/ops`, {
    method: "POST",
    headers: { ...auth, "content-type": "application/json" },
    body: JSON.stringify({
      write_id: "d".repeat(64),
      account_epoch: 7,
      domain: "tasks",
      op: {
        op: "create",
        record_id: "registered-door-test",
        content: createReadableTaskBag({ description: "registered door task", completed: false }),
      },
    }),
  });
  assert.equal(created.status, 200, await created.text());

  const [memories, tasks] = await Promise.all([
    fetch(`${listening.url}/v1/memories`, { headers: auth }),
    fetch(`${listening.url}/v1/tasks`, { headers: auth }),
  ]);
  assert.equal(memories.status, 200);
  assert.equal(tasks.status, 200);
  const page = await tasks.json();
  assert.equal(page.items[0].description, "registered door task");
  assert.equal(page.items[0].completed, false);
});

const fenceTally = (over = {}) => ({
  admitted: 2,
  refused: { authentication: 0, authorization: 0, entitlement: 0, stale_epoch: 1, control_unavailable: 0 },
  preservedEnvelopes: 1,
  ...over,
});

const writeOpsTally = (over = {}) => ({
  outcomes: {
    accepted: 1, accepted_idempotent: 1, authentication: 0, authorization: 0, entitlement: 0,
    stale_epoch: 1, validation: 0, write_id_reuse: 0, conflict: 0, control_unavailable: 0,
    ...(over.outcomes ?? {}),
  },
  preservedEnvelopes: over.preservedEnvelopes ?? 1,
});

/** The pair as `/v1/qa/control/stats?run=` returns it. */
const tally = (fenceOver = {}, writeOpsOver = {}) => ({
  fence: fenceTally(fenceOver),
  writeOps: writeOpsTally(writeOpsOver),
});

/**
 * A journey against an APPLYING door in which every assertion passes. Mutating
 * from a fully-green baseline is what makes each red-proof attributable to one
 * mutation rather than to the shape of the fixture.
 */
function appliedJourney(over = {}) {
  const createBody = JSON.stringify({
    write_id: WRITE_ID, account_epoch: 7, domain: "tasks",
    op: {
      op: "create",
      record_id: `task-journey-${RUN}`,
      content: createReadableTaskBag({ description: "t", completed: false }),
    },
  });
  const journey = {
    schema: 1,
    runId: RUN,
    door: { url: "http://127.0.0.1:4851", opsPath: "/v1/tasks/ops", capability: "applies", why: "its create response carries an `applied` block" },
    tree: { path: "/x/scripts/lint-import-graph.ts", registered: true },
    control: {
      url: "http://127.0.0.1:4851",
      seed: {
        accountId: "acct-dev-fixture",
        steps: [
          { name: "reset", response: { status: "reset" } },
          { name: "observe:legacy", response: { accepted: true } },
          { name: "activate", response: { activated: true } },
        ],
      },
    },
    epoch: { active: 7, stale: 6 },
    recordId: `task-journey-${RUN}`,
    steps: {
      create: {
        envelopeBuild: { ok: true, path: "/v1/tasks/ops" },
        request: { path: "/v1/tasks/ops", body: createBody, writeId: WRITE_ID, epoch: 7 },
        response: { status: 200, text: JSON.stringify({ applied: { record_id: `task-journey-${RUN}`, revision: REVISION }, idempotent: false }), retryAfter: null },
      },
      replay: {
        envelopeBuild: { ok: true, path: "/v1/tasks/ops" },
        request: { path: "/v1/tasks/ops", body: createBody, writeId: WRITE_ID, epoch: 7 },
        response: { status: 200, text: JSON.stringify({ applied: { record_id: `task-journey-${RUN}`, revision: REVISION }, idempotent: true }), retryAfter: null },
      },
      stale: {
        envelopeBuild: { ok: true, path: "/v1/tasks/ops" },
        request: { path: "/v1/tasks/ops", body: "{}", writeId: "b".repeat(64), epoch: 6 },
        response: { status: 409, text: STALE_BODY, retryAfter: null },
      },
      interleaved: {
        envelopeBuild: { ok: true, path: "/v1/tasks/ops" },
        request: { path: "/v1/tasks/ops", body: "{}", writeId: "c".repeat(64), epoch: 6 },
        response: { status: 409, text: STALE_BODY, retryAfter: null },
      },
    },
    producer: {
      thisRun: tally(),
      interleavedRun: tally(
        { admitted: 0, preservedEnvelopes: 1 },
        { outcomes: { accepted: 0, accepted_idempotent: 0 } },
      ),
      neverSentRun: { fence: null, writeOps: null },
    },
    // The consumer-side observation of the apply, from a different endpoint
    // over the same store, read after the refused patch.
    store: { records: [{ record_id: `task-journey-${RUN}`, revision: REVISION }] },
  };
  return { ...journey, ...over };
}

/** The stage-(a) shape: the fence harness door, no route registered. */
function fenceOnlyJourney() {
  const j = appliedJourney();
  j.door = { url: "http://127.0.0.1:4853", opsPath: "/v1/tasks/ops", capability: "fence-only", why: "admitted through the fence and applied nothing (`{fence:\"admitted\"}`)" };
  j.tree = { path: "/x/scripts/lint-import-graph.ts", registered: false };
  const admitted = JSON.stringify({ fence: "admitted", account_epoch: 7 });
  j.steps.create.response = { status: 202, text: admitted, retryAfter: null };
  j.steps.replay.response = { status: 202, text: admitted, retryAfter: null };
  // The retired harness had a fence counter and NOTHING else: no route outcome
  // counter and no store to observe. `null` says "this door cannot answer",
  // which is a different finding from a zero.
  j.producer.thisRun = { fence: fenceTally(), writeOps: null };
  j.producer.interleavedRun = { fence: fenceTally({ admitted: 0 }), writeOps: null };
  j.producer.neverSentRun = { fence: null, writeOps: null };
  j.store = { records: null };
  return j;
}

// ── The baseline must be green, or every red below proves nothing ───────────

test("baseline: an applying door passes every assertion", () => {
  const verdict = judge(appliedJourney());
  const notPass = verdict.assertions.filter((a) => a.result !== "pass");
  assert.deepEqual(notPass.map((a) => `${a.name}: ${a.detail}`), []);
  assert.equal(verdict.result, "pass");
  assert.equal(verdict.stage, "b");
});

test("baseline: the stage-(a) fence door passes everything the fence can answer, and PENDS the rest", () => {
  const verdict = judge(fenceOnlyJourney());
  assert.deepEqual(verdict.pending, ["server_applied_observation", "idempotent_replay"]);
  assert.equal(verdict.result, "partial");
  assert.equal(verdict.stage, "a");
  // PARTIAL IS NOT A PASS. This is the property the whole staging plan rests on.
  assert.notEqual(verdict.result, "pass");
  // …and the fence-answerable half is genuinely green, not skipped.
  for (const name of ["create_admitted", "stale_epoch_refused", "refusal_bytes_are_corpus_exact", "dead_letter_disposition", "join_is_by_run_id"]) {
    assert.equal(outcome(fenceOnlyJourney(), name).result, "pass", name);
  }
});

/**
 * A CHECKLIST, and labelled as one rather than dressed up as a proof: it fails
 * when someone adds a row to JOURNEY_ASSERTIONS without adding a red-proof
 * below. It cannot verify that the red-proofs are good — only that a new
 * assertion cannot arrive unaccompanied.
 */
const RED_PROOFED = new Set([
  "door_agreement", "control_seeded", "create_admitted", "server_applied_observation",
  "idempotent_replay", "stale_epoch_refused", "refusal_bytes_are_corpus_exact",
  "dead_letter_disposition", "join_is_by_run_id",
]);

test("no assertion arrives without a red-proof below", () => {
  assert.deepEqual(
    JOURNEY_ASSERTIONS.map((a) => a.name).filter((n) => !RED_PROOFED.has(n)),
    [],
    "an assertion with no red-proof in this file is a decoration",
  );
});

// ── Red-proofs ──────────────────────────────────────────────────────────────

test("RED-PROOF door_agreement: the route is registered but the journey drove the harness", () => {
  // The failure this exists for: OPS lands the route, STACK's journey keeps
  // pointing at the stage-(a) fence server, everything it can measure stays
  // green, and two of its steps stay PENDING forever while the report reads as
  // healthy progress.
  const j = fenceOnlyJourney();
  j.tree = { path: "/x", registered: true };
  const r = outcome(j, "door_agreement");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /STACK stage b/);
});

test("RED-PROOF door_agreement: a door applies writes for a path no registry row claims", () => {
  const j = appliedJourney();
  j.tree = { path: "/x", registered: false };
  assert.equal(outcome(j, "door_agreement").result, "fail");
});

test("RED-PROOF door_agreement: an unreadable door response is a failure, not a pending", () => {
  const j = appliedJourney();
  j.door = { ...j.door, capability: "unknown", why: "the create response is not JSON" };
  assert.equal(outcome(j, "door_agreement").result, "fail");
});

test("RED-PROOF control_seeded: the fence had nothing to admit against", () => {
  const j = appliedJourney();
  j.control.seed.steps[1].response = { accepted: false, reason: "out_of_order" };
  assert.equal(outcome(j, "control_seeded").result, "fail");
});

test("RED-PROOF create_admitted: the server's decision counter disagrees with the bytes received", () => {
  // A counter incremented at REQUEST ENTRY rather than at the decision would
  // report three for two admitted responses. `admitted > 0` cannot see that;
  // equality can.
  const j = appliedJourney();
  j.producer.thisRun = tally({ admitted: 3 }, { outcomes: { accepted: 2, accepted_idempotent: 1 } });
  const r = outcome(j, "create_admitted");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /arbiters disagree/);
});

test("RED-PROOF create_admitted: a broken run-id join is a failure, never an implied zero", () => {
  const j = appliedJourney();
  j.producer.thisRun = { fence: null, writeOps: null };
  const r = outcome(j, "create_admitted");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /null, not zero/);
});

test("RED-PROOF server_applied_observation: the door applied to a different record", () => {
  const j = appliedJourney();
  j.steps.create.response.text = JSON.stringify({ applied: { record_id: "task-somebody-else", revision: REVISION }, idempotent: false });
  assert.equal(outcome(j, "server_applied_observation").result, "fail");
});

test("RED-PROOF server_applied_observation: the door says it applied and the store does not have it", () => {
  // THE one this assertion exists for. A route that answers `{applied: …}`
  // built from the request it was handed, having written nothing, passes every
  // check that reads only the door's own response.
  const j = appliedJourney();
  j.store = { records: [] };
  const r = outcome(j, "server_applied_observation");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /the store does not contain it/);
});

test("RED-PROOF server_applied_observation: the refused patch applied anyway", () => {
  // The store is read AFTER the stale patch is refused, so a revision that has
  // moved on means the refusal did not prevent the write. That is a straggler
  // silently landing in a superseded generation — the thing the fence exists
  // to make impossible.
  const j = appliedJourney();
  j.store = { records: [{ record_id: `task-journey-${RUN}`, revision: "f".repeat(64) }] };
  const r = outcome(j, "server_applied_observation");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /refusal applied anyway/);
});

test("RED-PROOF server_applied_observation: the store could not be observed at all", () => {
  const j = appliedJourney();
  j.store = { records: { unobservable: "control /v1/qa/control/tasks -> 404" } };
  const r = outcome(j, "server_applied_observation");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /no second measurement/);
});

test("RED-PROOF create_admitted: the fence admitted but the route never accepted", () => {
  // Admitted-through-the-fence and applied are different events. A door that
  // clears the fence and then fails to apply moves only the first counter, and
  // a journey reading one tally would call that a working write path.
  const j = appliedJourney();
  j.producer.thisRun = tally({ admitted: 2 }, { outcomes: { accepted: 0, accepted_idempotent: 0 } });
  const r = outcome(j, "create_admitted");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /not the same event as applied/);
});

test("RED-PROOF idempotent_replay: the wire flag and the recorded outcome disagree", () => {
  const j = appliedJourney();
  j.producer.thisRun = tally({}, { outcomes: { accepted: 2, accepted_idempotent: 0 } });
  const r = outcome(j, "idempotent_replay");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /disagree/);
});

test("RED-PROOF stale_epoch_refused: the fence decided stale and the wire reported something else", () => {
  const j = appliedJourney();
  j.producer.thisRun = tally({}, { outcomes: { stale_epoch: 0, conflict: 1 } });
  const r = outcome(j, "stale_epoch_refused");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /did not reach the wire as the class the fence decided/);
});

test("RED-PROOF dead_letter_disposition: the fence preserved and the straggler table did not", () => {
  const j = appliedJourney();
  j.producer.thisRun = tally({ preservedEnvelopes: 1 }, { preservedEnvelopes: 0 });
  const r = outcome(j, "dead_letter_disposition");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /disagree about the same refusal/);
});

test("RED-PROOF idempotent_replay: the registry did not recognise the replayed write_id", () => {
  // B1's demonstrated failure: applied, crashed before the tombstone, replayed.
  // A door that reports a fresh apply on replay has applied the op twice.
  const j = appliedJourney();
  j.steps.replay.response.text = JSON.stringify({ applied: { record_id: `task-journey-${RUN}`, revision: REVISION }, idempotent: false });
  const r = outcome(j, "idempotent_replay");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /applied twice/);
});

test("RED-PROOF idempotent_replay: the FIRST send already claimed idempotent", () => {
  const j = appliedJourney();
  j.steps.create.response.text = JSON.stringify({ applied: { record_id: `task-journey-${RUN}`, revision: REVISION }, idempotent: true });
  assert.equal(outcome(j, "idempotent_replay").result, "fail");
});

test("RED-PROOF idempotent_replay: a replay that did not send identical bytes proves nothing", () => {
  const j = appliedJourney();
  j.steps.replay.request.body = `${j.steps.replay.request.body} `;
  assert.equal(outcome(j, "idempotent_replay").result, "fail");
});

test("RED-PROOF stale_epoch_refused: a refusal with no paired admission is indistinguishable from a broken door", () => {
  // The whole point. A 404, a crash, a typo'd path and a server refusing
  // everything all satisfy "not 2xx"; none of them can also produce the 202.
  const j = appliedJourney();
  j.steps.create.response = { status: 404, text: '{"error":"not_found"}', retryAfter: null };
  const r = outcome(j, "stale_epoch_refused");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /indistinguishable/);
});

test("RED-PROOF stale_epoch_refused: refused, but not by the fence", () => {
  const j = appliedJourney();
  j.producer.thisRun = tally({ refused: { authentication: 0, authorization: 0, entitlement: 0, stale_epoch: 0, control_unavailable: 0 } }, { outcomes: { stale_epoch: 0 } });
  assert.equal(outcome(j, "stale_epoch_refused").result, "fail");
});

test("RED-PROOF stale_epoch_refused: the corpus status is the arbiter, not the driver's expectation", () => {
  const j = appliedJourney();
  j.steps.stale.response.status = 403;
  assert.equal(outcome(j, "stale_epoch_refused").result, "fail");
});

test("RED-PROOF refusal_bytes_are_corpus_exact: an extra field in the refusal body", () => {
  const j = appliedJourney();
  j.steps.stale.response.text = JSON.stringify({ error: "stale_epoch", refusal_outcome: "stale_epoch", detail: "epoch 6 < 7" });
  assert.equal(outcome(j, "refusal_bytes_are_corpus_exact").result, "fail");
});

test("RED-PROOF refusal_bytes_are_corpus_exact: the leak check fires even on corpus-exact bytes", () => {
  // W1's load-bearing condition, and ADR-012 §4's: a caller without authority
  // over the account must not be able to probe migration progress off a
  // refusal. The byte-compare above cannot cover this on its own — a body can
  // be corpus-exact and still contain the account's own identifier if the
  // identifier happens to be a substring of it. So the leak scan runs
  // independently, and this mutation makes the account id a substring of the
  // ratified body to prove the scan is live rather than shadowed by the
  // byte-compare.
  const j = appliedJourney();
  j.control.seed.accountId = "stale_epoch";
  assert.equal(j.steps.stale.response.text, STALE_BODY, "the bytes are still corpus-exact");
  const r = outcome(j, "refusal_bytes_are_corpus_exact");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /leaks/);
});

test("RED-PROOF dead_letter_disposition: the straggler's envelope was not preserved", () => {
  // A straggler refused and NOT preserved is a silently lost edit — the one
  // refusal class that is supposed to keep the user's content recoverable.
  const j = appliedJourney();
  j.producer.thisRun = tally({ preservedEnvelopes: 0 }, { preservedEnvelopes: 0 });
  const r = outcome(j, "dead_letter_disposition");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /silently lost edit/);
});

test("RED-PROOF dead_letter_disposition: the shipped client would call it a conflict", () => {
  // B2 rules `conflict` out by name: telling a person their saved edit
  // conflicted, when the server refused an op authored in a superseded
  // generation, is a false report about their own content.
  const j = appliedJourney();
  const verdict = judgeJourney(j, { corpus, classify: () => ({ kind: "permanent", reason: "conflict", detail: "x" }) });
  const r = verdict.assertions.find((a) => a.name === "dead_letter_disposition");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /B2 rules out/);
});

test("RED-PROOF dead_letter_disposition: a classifier that reads the refusal as success", () => {
  const j = appliedJourney();
  const verdict = judgeJourney(j, { corpus, classify: () => null });
  assert.equal(verdict.assertions.find((a) => a.name === "dead_letter_disposition").result, "fail");
});

test("RED-PROOF join_is_by_run_id: a counter that reports the same tally for every run", () => {
  // Without this probe, a counter hard-coded to return one admitted and one
  // stale_epoch would satisfy every other assertion in this file.
  const j = appliedJourney();
  j.producer.neverSentRun = tally();
  const r = outcome(j, "join_is_by_run_id");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /reports N for everything/);
});

test("RED-PROOF join_is_by_run_id: an all-zero tally is not the same finding as null", () => {
  const j = appliedJourney();
  j.producer.neverSentRun = tally({ admitted: 0, refused: { authentication: 0, authorization: 0, entitlement: 0, stale_epoch: 0, control_unavailable: 0 }, preservedEnvelopes: 0 }, { outcomes: { accepted: 0, accepted_idempotent: 0, stale_epoch: 0 }, preservedEnvelopes: 0 });
  assert.equal(outcome(j, "join_is_by_run_id").result, "fail");
});

test("RED-PROOF join_is_by_run_id: this run's tally absorbed another run's traffic", () => {
  const j = appliedJourney();
  j.producer.thisRun = tally({ refused: { authentication: 0, authorization: 0, entitlement: 0, stale_epoch: 2, control_unavailable: 0 } }, { outcomes: { stale_epoch: 2 } });
  const r = outcome(j, "join_is_by_run_id");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /absorbed/);
});

// ── Properties of the verdict itself ────────────────────────────────────────

test("an assertion that throws is reported as a failure, and does not erase the others", () => {
  const j = appliedJourney();
  j.steps.stale.response = null;
  const verdict = judge(j);
  assert.equal(verdict.assertions.length, JOURNEY_ASSERTIONS.length);
  assert.equal(verdict.result, "fail");
});

test("gating is derived from the registry row, never declared", () => {
  assert.equal(gatingOf({ tree: { registered: true }, door: { opsPath: "/v1/tasks/ops" } }).gating, true);
  const off = gatingOf(fenceOnlyJourney());
  assert.equal(off.gating, false);
  assert.match(off.gatingNote, /gates automatically/);
});

test("classifyDoor reads the capability off the bytes, and calls unrecognised bytes unknown", () => {
  assert.equal(classifyDoor({ text: '{"applied":{"record_id":"r","revision":null},"idempotent":false}' }).capability, "applies");
  assert.equal(classifyDoor({ text: '{"fence":"admitted","account_epoch":7}' }).capability, "fence-only");
  assert.equal(classifyDoor({ text: "not json" }).capability, "unknown");
  assert.equal(classifyDoor({ text: '{"ok":true}' }).capability, "unknown");
});

test("mintWriteId produces the ratified 64-lowercase-hex shape", () => {
  const id = mintWriteId();
  assert.match(id, new RegExp(corpus.writeIdPattern));
  assert.notEqual(id, mintWriteId());
});

// ── STAGE (c): the outbox drain's verdict path ──────────────────────────────
// Same standard: one mutation per assertion, each required to go red, from a
// baseline that is green first.
//
// The EXPENSIVE half of these three was not staged — it was observed. Two real
// defects in this stage's own driver produced all three reds live against the
// registered door before the stage ever passed:
//   * the journaled payload built as a WIRE op instead of the client's own
//     TaskOp — `taskOpToWriteOp` returned null, nothing was sent, and
//     `outbox_drained_to_the_door` went red naming a null server tally;
//   * `env.advance()` called once, on the assumption a send settles inside it.
//     Over real HTTP the next timer is only scheduled after the previous send
//     resolves, so the retry ladder never ran: `journaled_write_id…` and
//     `straggler_dead_letters…` both went red, correctly, on an outbox that had
//     simply not been given time.
// Both were found by the assertions, not by reading the driver.

const outboxFacts = (over = {}) => ({
  drainRunId: "run-x-outbox",
  staleRunId: "run-x-outbox-stale",
  recordId: "flying-dragon-vibrant",
  journaled: { count: 1, writeId: "a".repeat(64), accountEpoch: 7, opId: "outbox-op-1" },
  deadAfterDrain: [],
  deadLetters: [{ opId: "outbox-op-stale", failure: { kind: "permanent", reason: "stale_epoch" } }],
  controlRefreshes: [],
  staleJournaled: { count: 1, writeId: "b".repeat(64), accountEpoch: 6, opId: "outbox-op-stale" },
  epoch: { active: 7, straggler: 6 },
  staleResponse: {
    method: "POST", path: "/v1/tasks/ops", status: 409, text: STALE_BODY,
    body: { write_id: "b".repeat(64), account_epoch: 6, domain: "tasks", op: { op: "create", record_id: "flying-dragon-vibrant", content: {} } },
  },
  drainWire: {
    method: "POST", path: "/v1/tasks/ops", status: 200,
    body: { write_id: "a".repeat(64), account_epoch: 7, domain: "tasks", op: { op: "create", record_id: "flying-dragon-vibrant", content: {} } },
  },
  replayResponse: { status: 200, text: JSON.stringify({ applied: { record_id: "flying-dragon-vibrant", revision: REVISION }, idempotent: true }) },
  ...over,
});

const outboxProducer = (over = {}) => ({
  drain: { fence: fenceTally(), writeOps: writeOpsTally() },
  stale: { fence: fenceTally({ admitted: 0 }), writeOps: writeOpsTally({ outcomes: { accepted: 0, accepted_idempotent: 0 } }) },
  ...over,
});

const outboxOutcome = (facts, producer, name) =>
  judgeOutbox(facts, { producer, corpus }).assertions.find((a) => a.name === name);

test("stage (c) baseline: a clean outbox drain passes every assertion", () => {
  const v = judgeOutbox(outboxFacts(), { producer: outboxProducer(), corpus });
  assert.deepEqual(v.assertions.filter((a) => a.result !== "pass").map((a) => `${a.name}: ${a.detail}`), []);
  assert.equal(v.result, "pass");
});

test("RED-PROOF outbox_drained_to_the_door: the outbox journaled an op and sent nothing", () => {
  const p = outboxProducer({ drain: { fence: null, writeOps: null } });
  const r = outboxOutcome(outboxFacts(), p, "outbox_drained_to_the_door");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /null, not zero/);
});

test("RED-PROOF outbox_drained_to_the_door: the server accepted and the client dead-lettered the same op", () => {
  const r = outboxOutcome(outboxFacts({ deadAfterDrain: [{ opId: "outbox-op-1" }] }), outboxProducer(), "outbox_drained_to_the_door");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /disagree about the same op/);
});

test("RED-PROOF journaled_write_id: the id was minted at send time, not at enqueue", () => {
  // B1's demonstrated failure. The server does not recognise an id the client
  // had already used, so the crash-replayed op applies a second time and the
  // user's edit is duplicated.
  const facts = outboxFacts({
    drainWire: {
    method: "POST", path: "/v1/tasks/ops", status: 200,
    body: { write_id: "a".repeat(64), account_epoch: 7, domain: "tasks", op: { op: "create", record_id: "flying-dragon-vibrant", content: {} } },
  },
  replayResponse: { status: 200, text: JSON.stringify({ applied: { record_id: "flying-dragon-vibrant", revision: REVISION }, idempotent: false }) },
  });
  const r = outboxOutcome(facts, outboxProducer(), "journaled_write_id_is_the_one_the_server_registered");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /send-time mint/);
});

test("RED-PROOF journaled_write_id: nothing was journaled at all", () => {
  const r = outboxOutcome(outboxFacts({ journaled: { count: 1, writeId: null, accountEpoch: 7 } }), outboxProducer(), "journaled_write_id_is_the_one_the_server_registered");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /minted at enqueue/);
});

test("RED-PROOF journaled_write_id: no account epoch was journaled with the op", () => {
  const r = outboxOutcome(outboxFacts({ journaled: { count: 1, writeId: "a".repeat(64), accountEpoch: null } }), outboxProducer(), "journaled_write_id_is_the_one_the_server_registered");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /straggler stamp/);
});

test("RED-PROOF straggler_dead_letters_as_stale_epoch: the server refused and the client dropped it", () => {
  // An op refused server-side and dropped client-side is a user's edit that
  // vanished with no surface to recover it from.
  const r = outboxOutcome(outboxFacts({ deadLetters: [] }), outboxProducer(), "straggler_dead_letters_as_stale_epoch");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /vanished with no surface/);
});

test("RED-PROOF straggler_dead_letters_as_stale_epoch: the client called it a conflict", () => {
  const facts = outboxFacts({ deadLetters: [{ opId: "outbox-op-stale", failure: { kind: "permanent", reason: "conflict" } }] });
  const r = outboxOutcome(facts, outboxProducer(), "straggler_dead_letters_as_stale_epoch");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /B2 rules out/);
});

test("RED-PROOF straggler_dead_letters_as_stale_epoch: the straggler was treated as backpressure", () => {
  // W1's `control_unavailable` is retryable and is never a dead letter;
  // `stale_epoch` is permanent and always is. Handling one as the other either
  // loses the edit or retries forever against a server that cannot accept it.
  const r = outboxOutcome(outboxFacts({ controlRefreshes: ["outbox-op-stale"] }), outboxProducer(), "straggler_dead_letters_as_stale_epoch");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /not backpressure/);
});

test("RED-PROOF straggler_dead_letters_as_stale_epoch: refused but not preserved", () => {
  const p = outboxProducer({ stale: { fence: fenceTally({ admitted: 0, preservedEnvelopes: 0 }), writeOps: null } });
  const r = outboxOutcome(outboxFacts(), p, "straggler_dead_letters_as_stale_epoch");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /silently lost edit/);
});

test("RED-PROOF straggler_wire_matches_its_journal: the epoch was re-stamped at send time", () => {
  // B1's second named failure, and the one the other three arbiters cannot see:
  // the provider is behind either way, so the fence still refuses, the envelope
  // is still preserved, and the client still dead-letters correctly — while the
  // field that decides which generation an op belongs to is wrong.
  const f = outboxFacts();
  f.staleResponse = { ...f.staleResponse, body: { ...f.staleResponse.body, account_epoch: 7 } };
  const r = outboxOutcome(f, outboxProducer(), "straggler_wire_matches_its_journal");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /AUTHORED under/);
});

test("RED-PROOF straggler_wire_matches_its_journal: the write id on the wire is not the journaled one", () => {
  const f = outboxFacts();
  f.staleResponse = { ...f.staleResponse, body: { ...f.staleResponse.body, write_id: "c".repeat(64) } };
  const r = outboxOutcome(f, outboxProducer(), "straggler_wire_matches_its_journal");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /minted at send time/);
});

test("RED-PROOF straggler_wire_matches_its_journal: the straggler never left the client", () => {
  // The fence tally and the dead letter are both satisfiable by a run in which
  // nothing was sent. This is the row that says the op reached the wire.
  const r = outboxOutcome(outboxFacts({ staleResponse: null }), outboxProducer(), "straggler_wire_matches_its_journal");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /never reached the wire/);
});

test("RED-PROOF straggler_wire_matches_its_journal: the 'straggler' was not actually superseded", () => {
  const f = outboxFacts();
  f.staleJournaled = { ...f.staleJournaled, accountEpoch: 7 };
  f.staleResponse = { ...f.staleResponse, body: { ...f.staleResponse.body, account_epoch: 7 } };
  const r = outboxOutcome(f, outboxProducer(), "straggler_wire_matches_its_journal");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /proves nothing about stragglers/);
});

test("RED-PROOF straggler_wire_matches_its_journal: the transport received bytes the door does not send", () => {
  // `stale_epoch` and `conflict` are both 409 and differ only in the body, which
  // is why sendPlatformTaskOp calls the `text` requirement load-bearing. A
  // classification can be right for the wrong input; this pins the input.
  const f = outboxFacts();
  f.staleResponse = { ...f.staleResponse, text: JSON.stringify({ error: "conflict" }) };
  const r = outboxOutcome(f, outboxProducer(), "straggler_wire_matches_its_journal");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /not the ratified refusal/);
});

test("RED-PROOF journaled_write_id: the outbox re-stamped the epoch on its way out", () => {
  // B1's other named failure, invisible to any server-side answer: the fence
  // admits either way, so only the journal-vs-wire comparison can see it.
  const f = outboxFacts();
  f.drainWire = { ...f.drainWire, body: { ...f.drainWire.body, account_epoch: 9 } };
  const r = outboxOutcome(f, outboxProducer(), "journaled_write_id_is_the_one_the_server_registered");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /re-stamping at send time/);
});

test("RED-PROOF journaled_write_id: the outbox sent an id its journal does not hold", () => {
  const f = outboxFacts();
  f.drainWire = { ...f.drainWire, body: { ...f.drainWire.body, write_id: "e".repeat(64) } };
  const r = outboxOutcome(f, outboxProducer(), "journaled_write_id_is_the_one_the_server_registered");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /minted at send time/);
});

test("RED-PROOF journaled_write_id: the outbox put nothing readable on the wire", () => {
  const r = outboxOutcome(outboxFacts({ drainWire: null }), outboxProducer(), "journaled_write_id_is_the_one_the_server_registered");
  assert.equal(r.result, "fail");
  assert.match(r.detail, /no readable envelope/);
});
