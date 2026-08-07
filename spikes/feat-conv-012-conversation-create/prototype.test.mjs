import assert from "node:assert/strict";
import { test } from "node:test";

import { FixtureError } from "./lib.mjs";
import { ClientIdCreatePrototype } from "./prototypes/client-id-create.mjs";
import { HybridPrototype } from "./prototypes/hybrid.mjs";
import { PipelineEntryPrototype } from "./prototypes/pipeline-entry.mjs";

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

test("A: a lost processor after admission cannot be recovered by retrying the current-pointer entry", () => {
  const fixture = new PipelineEntryPrototype();
  const captured = fixture.capture("u1", [{ text: "server capture" }]);
  expectFixtureError(() => fixture.finalizeCurrent("u1", { failAfterAdmission: true }), 503, "processor-crashed");
  assert.equal(fixture.get("u1", captured.id).status, "processing");
  expectFixtureError(() => fixture.finalizeCurrent("u1"), 404, "in-progress-not-found");
});

test("B: client create accepts UUID or word-slug ids and rejects arbitrary ids", () => {
  const fixture = new ClientIdCreatePrototype();
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

test("B: same opId replays exactly; changed input is a terminal 409", () => {
  const fixture = new ClientIdCreatePrototype();
  const op = { opId: "create-1", id: "quiet-river-stone", segments: [{ text: "offline" }], startedAt: 1 };
  const first = fixture.create("u1", op);
  const replay = fixture.create("u1", op);
  assert.deepEqual(replay, first);
  assert.equal(fixture.ledgerSize, 1);
  expectFixtureError(
    () => fixture.create("u1", { ...op, segments: [{ text: "different" }] }),
    409,
    "op-id-reused",
  );
});

test("B: create identity conflicts are explicit and a failed processor can resume with the same opId", () => {
  const fixture = new ClientIdCreatePrototype();
  fixture.create("u1", {
    opId: "create-1",
    id: "quiet-river-stone",
    segments: [{ text: "offline" }],
    startedAt: 1,
  });
  expectFixtureError(
    () =>
      fixture.create("u1", {
        opId: "create-2",
        id: "quiet-river-stone",
        segments: [{ text: "other" }],
        startedAt: 1,
      }),
    409,
    "record-id-conflict",
  );
  expectFixtureError(
    () => fixture.process("u1", { opId: "process-1", id: "quiet-river-stone", failAfterAdmission: true }),
    503,
    "processor-crashed",
  );
  const recovered = fixture.process("u1", { opId: "process-1", id: "quiet-river-stone" });
  assert.equal(recovered.record.status, "completed");
  assert.equal(recovered.record.processingRuns, 2);
});

test("C: an offline client record can later receive pipeline capture under one identity", () => {
  const fixture = new HybridPrototype();
  fixture.createOffline("u1", { opId: "client-1", id: "quiet-river-stone", startedAt: 1 });
  const ingested = fixture.ingestCapture("u1", {
    opId: "ingest-1",
    id: "quiet-river-stone",
    captureId: "capture-1",
    startedAt: 1,
    segments: [{ text: "server transcript" }],
  });
  assert.equal(ingested.status, 200);
  assert.equal(ingested.record.origin, "client");
  assert.equal(ingested.record.captureId, "capture-1");
  assert.equal(ingested.record.status, "completed");
  assert.deepEqual(fixture.ingestCapture("u1", {
    opId: "ingest-1",
    id: "quiet-river-stone",
    captureId: "capture-1",
    startedAt: 1,
    segments: [{ text: "server transcript" }],
  }), ingested);
});

test("C: pipeline-only creation works, while ambiguous content and identity bindings fail closed", () => {
  const fixture = new HybridPrototype();
  const pipelineOnly = fixture.ingestCapture("u1", {
    opId: "ingest-1",
    captureId: "capture-1",
    startedAt: 1,
    segments: [{ text: "server transcript" }],
  });
  assert.equal(pipelineOnly.status, 201);
  assert.equal(pipelineOnly.record.origin, "pipeline");
  assert.deepEqual(
    fixture.ingestCapture("u1", {
      opId: "ingest-1",
      captureId: "capture-1",
      startedAt: 1,
      segments: [{ text: "server transcript" }],
    }),
    pipelineOnly,
    "pipeline-generated identity must remain stable when a committed response is lost",
  );

  fixture.createOffline("u1", {
    opId: "client-1",
    id: "quiet-river-stone",
    startedAt: 2,
    segments: [{ text: "client transcript" }],
  });
  expectFixtureError(
    () =>
      fixture.ingestCapture("u1", {
        opId: "ingest-2",
        id: "quiet-river-stone",
        captureId: "capture-2",
        startedAt: 2,
        segments: [{ text: "different server transcript" }],
      }),
    409,
    "content-reconciliation-needs-ruling",
  );
  expectFixtureError(
    () =>
      fixture.ingestCapture("u1", {
        opId: "ingest-3",
        id: "amber-forest-field",
        captureId: "capture-1",
        startedAt: 1,
        segments: [{ text: "server transcript" }],
      }),
    409,
    "capture-binding-conflict",
  );
});
