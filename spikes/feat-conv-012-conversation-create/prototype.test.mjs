import assert from "node:assert/strict";
import { test } from "node:test";

import { FixtureError, OperationLedger } from "./lib.mjs";
import { ClientIdCreatePrototype } from "./prototypes/client-id-create.mjs";
import { HybridPrototype } from "./prototypes/hybrid.mjs";
import { PipelineEntryPrototype } from "./prototypes/pipeline-entry.mjs";

const fixtureScope = { tenantId: "tenant-a", domain: "conversations" };

function clientFixture(scope = fixtureScope) {
  return new ClientIdCreatePrototype(scope);
}

function hybridFixture(scope = fixtureScope) {
  return new HybridPrototype(scope);
}

function expectFixtureError(fn, status, code) {
  assert.throws(fn, (error) => error instanceof FixtureError && error.status === status && error.code === code);
}

test("A: pipeline entry requires a pre-existing server-owned current record", () => {
  const fixture = new PipelineEntryPrototype();
  expectFixtureError(() => fixture.finalizeCurrent("u1"), 404, "in-progress-not-found");
  const captured = fixture.capture("u1", [{ text: "server capture" }]);
  const finalized = fixture.finalizeCurrent("u1");
  assert.equal(finalized.id, captured.id);
  assert.equal(finalized.status, "completed");
  assert.equal(finalized.processingRuns, 1);
});

test("A: a handled processor exception rolls admission back and DB fallback makes retry possible", () => {
  const fixture = new PipelineEntryPrototype();
  const captured = fixture.capture("u1", [{ text: "server capture" }]);
  expectFixtureError(
    () => fixture.finalizeCurrent("u1", { failAfterAdmission: "handled-exception" }),
    503,
    "processor-failed",
  );
  assert.equal(fixture.get("u1", captured.id).status, "in_progress");
  const retried = fixture.finalizeCurrent("u1");
  assert.equal(retried.status, "completed");
  assert.equal(retried.processingRuns, 2);
});

test("A: only a hard process crash leaves a processing orphan for stale recovery", () => {
  const fixture = new PipelineEntryPrototype();
  const captured = fixture.capture("u1", [{ text: "server capture" }]);
  expectFixtureError(
    () => fixture.finalizeCurrent("u1", { failAfterAdmission: "hard-crash" }),
    503,
    "processor-hard-crashed",
  );
  assert.equal(fixture.get("u1", captured.id).status, "processing");
  expectFixtureError(() => fixture.finalizeCurrent("u1"), 404, "in-progress-not-found");
  assert.equal(fixture.recoverStaleOrphan("u1", captured.id), true);
  assert.equal(fixture.get("u1", captured.id).status, "completed");
});

test("operation receipt scope is parameterized by tenant, user, and domain", () => {
  const ledger = new OperationLedger();
  const seen = [];
  const run = (scope, label) => ledger.run(scope, "same-op", { mutation: "create" }, () => seen.push(label));
  run({ tenantId: "t1", userId: "u1", domain: "conversations" }, "t1-u1-conv");
  run({ tenantId: "t2", userId: "u1", domain: "conversations" }, "t2-u1-conv");
  run({ tenantId: "t1", userId: "u2", domain: "conversations" }, "t1-u2-conv");
  run({ tenantId: "t1", userId: "u1", domain: "tasks" }, "t1-u1-task");
  assert.deepEqual(seen, ["t1-u1-conv", "t2-u1-conv", "t1-u2-conv", "t1-u1-task"]);
  assert.equal(ledger.size(), 4);
});

test("B: client create accepts UUID or word-slug ids and rejects arbitrary ids", () => {
  const fixture = clientFixture();
  const created = fixture.create("u1", {
    opId: "create-1",
    id: "quiet-river-stone",
    segments: [{ text: "offline" }],
    startedAt: 1,
  });
  assert.equal(created.status, 201);
  const uuidCreated = fixture.create("u1", {
    opId: "create-2",
    id: "2f1a6f0e-8f4b-4a4e-9c39-88b0d5e2a111",
    segments: [],
    startedAt: 2,
  });
  assert.equal(uuidCreated.status, 201);
  expectFixtureError(
    () => fixture.create("u1", { opId: "create-3", id: "bad", segments: [], startedAt: 3 }),
    422,
    "invalid-record-id",
  );
});

test("B: same successful opId replays exactly; changed input is a terminal 409", () => {
  const fixture = clientFixture();
  const op = { opId: "create-1", id: "quiet-river-stone", segments: [{ text: "offline" }], startedAt: 1 };
  const first = fixture.create("u1", op);
  assert.deepEqual(fixture.create("u1", op), first);
  expectFixtureError(
    () => fixture.create("u1", { ...op, segments: [{ text: "different" }] }),
    409,
    "op-id-reused",
  );
});

test("B: a first terminal conflict is stored and cannot become success under that opId", () => {
  const fixture = clientFixture();
  const seed = {
    opId: "seed",
    id: "quiet-river-stone",
    segments: [{ text: "authoritative" }],
    startedAt: 1,
  };
  fixture.create("u1", seed);
  const conflicting = { ...seed, opId: "conflict", segments: [{ text: "conflicting" }] };
  expectFixtureError(() => fixture.create("u1", conflicting), 409, "record-id-conflict");
  expectFixtureError(() => fixture.create("u1", conflicting), 409, "record-id-conflict");
  expectFixtureError(() => fixture.create("u1", { ...seed, opId: "conflict" }), 409, "op-id-reused");
  assert.equal(fixture.get("u1", seed.id).createPayload.segments[0].text, "authoritative");
});

test("B: a failed processor can resume with the same opId without changing create identity", () => {
  const fixture = clientFixture();
  fixture.create("u1", {
    opId: "create-1",
    id: "quiet-river-stone",
    segments: [{ text: "offline" }],
    startedAt: 1,
  });
  expectFixtureError(
    () => fixture.process("u1", { opId: "process-1", id: "quiet-river-stone", failAfterAdmission: true }),
    503,
    "processor-crashed",
  );
  const recovered = fixture.process("u1", { opId: "process-1", id: "quiet-river-stone" });
  assert.equal(recovered.record.status, "completed");
  assert.equal(recovered.record.processingRuns, 2);
});

// domain-pending(FEAT-CONV-012): hybrid binding and metadata names below are spike vocabulary only.
test("C: client identity binds to matching capture metadata before separate finalization", () => {
  const fixture = hybridFixture();
  fixture.createOffline("u1", {
    opId: "client-1",
    id: "quiet-river-stone",
    startedAt: 1,
    source: "phone",
    captureDeviceId: "device-1",
  });
  const bound = fixture.bindCapture("u1", {
    opId: "bind-1",
    id: "quiet-river-stone",
    captureId: "capture-1",
    startedAt: 1,
    source: "phone",
    captureDeviceId: "device-1",
    segments: [{ text: "server transcript" }],
  });
  assert.equal(bound.record.status, "in_progress", "binding is not finalization");
  assert.equal(bound.record.captureId, "capture-1");
  const admitted = fixture.admitFinalization("u1", { opId: "finalize-1", id: "quiet-river-stone" });
  assert.equal(admitted.record.status, "processing");
  assert.equal(admitted.job.status, "queued");
  const completed = fixture.runFinalizer("u1", "quiet-river-stone");
  assert.equal(completed.record.status, "completed");
  assert.equal(completed.job.status, "completed");
});

// domain-pending(FEAT-CONV-012): pipeline-created identity and captureId are provisional.
test("C: pipeline-only binding has stable identity across lost-response replay", () => {
  const fixture = hybridFixture();
  const op = {
    opId: "bind-1",
    captureId: "capture-1",
    startedAt: 1,
    source: "phone",
    captureDeviceId: "device-1",
    segments: [{ text: "server transcript" }],
  };
  const first = fixture.bindCapture("u1", op);
  assert.equal(first.status, 201);
  assert.equal(first.record.origin, "pipeline");
  assert.deepEqual(fixture.bindCapture("u1", op), first);
});

// domain-pending(FEAT-CONV-012): timestamp/source/device matching tolerance needs David's ruling.
test("C: binding fails closed when identity-bearing capture metadata differs", () => {
  const fixture = hybridFixture();
  fixture.createOffline("u1", {
    opId: "client-1",
    id: "quiet-river-stone",
    startedAt: 1,
    source: "phone",
    captureDeviceId: "device-1",
  });
  const mismatched = {
    opId: "bind-mismatch",
    id: "quiet-river-stone",
    captureId: "capture-1",
    startedAt: 2,
    source: "phone",
    captureDeviceId: "device-1",
    segments: [{ text: "server transcript" }],
  };
  expectFixtureError(() => fixture.bindCapture("u1", mismatched), 409, "capture-metadata-needs-ruling");
  expectFixtureError(() => fixture.bindCapture("u1", mismatched), 409, "capture-metadata-needs-ruling");
  expectFixtureError(
    () => fixture.bindCapture("u1", { ...mismatched, startedAt: 1 }),
    409,
    "op-id-reused",
  );
});

// domain-pending(FEAT-CONV-012): capture content reconciliation remains undecided.
test("C: ambiguous client and pipeline content fails closed", () => {
  const fixture = hybridFixture();
  fixture.createOffline("u1", {
    opId: "client-1",
    id: "quiet-river-stone",
    startedAt: 1,
    source: "phone",
    captureDeviceId: "device-1",
    segments: [{ text: "client transcript" }],
  });
  expectFixtureError(
    () =>
      fixture.bindCapture("u1", {
        opId: "bind-1",
        id: "quiet-river-stone",
        captureId: "capture-1",
        startedAt: 1,
        source: "phone",
        captureDeviceId: "device-1",
        segments: [{ text: "different server transcript" }],
      }),
    409,
    "content-reconciliation-needs-ruling",
  );
});

test("C: a hard-crashed finalizer is retried through a new lease, not through binding", () => {
  const fixture = hybridFixture();
  const bound = fixture.bindCapture("u1", {
    opId: "bind-1",
    captureId: "capture-1",
    startedAt: 1,
    source: "phone",
    segments: [{ text: "server transcript" }],
  });
  fixture.admitFinalization("u1", { opId: "finalize-1", id: bound.record.id });
  expectFixtureError(() => fixture.runFinalizer("u1", bound.record.id, { hardCrash: true }), 503, "finalizer-hard-crashed");
  expectFixtureError(() => fixture.runFinalizer("u1", bound.record.id), 503, "finalization-lease-active");
  const recovered = fixture.runFinalizer("u1", bound.record.id, { reclaimExpired: true });
  assert.equal(recovered.record.status, "completed");
  assert.equal(recovered.job.leaseEpoch, 2);
});
