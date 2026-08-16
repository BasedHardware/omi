/**
 * The client half of `POST /v1/stm-notes/ops` — the HTTP write door for a
 * user-asserted fact. Drives the real envelope builder and sender over a
 * scripted HTTP boundary. Empty text is refused locally because there is
 * nothing to seal; the user's words are otherwise sent as written.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  STM_NOTES_OPS_PATH,
  WRITE_ID_ENTROPY_BYTES,
  buildStmNoteCreateEnvelope,
  createDevAccountEpochProvider,
  observeAccountEpochFromTasksRead,
  sendUserAssertedStmNote,
} from "@omi-core/adapters-platform";
import { MemoryCorrectionStore } from "@omi-core/domain";
import { WRITE_ERRORS, WRITE_ID_PATTERN, mintWriteId } from "@omi-core/ratified-contracts/write/ops";
import { ScriptedHttp } from "../fakes.js";

const FACT = "Atlas likes oat milk at Harborline Cafe";
const ENTROPY = new Uint8Array(WRITE_ID_ENTROPY_BYTES).fill(0xab);
const WRITE_ID = mintWriteId(ENTROPY)!;

const accepted = (recordId: string) => ({
  status: 200,
  json: { applied: { record_id: recordId, revision: "c".repeat(64) }, idempotent: false },
  text: JSON.stringify({ applied: { record_id: recordId, revision: "c".repeat(64) }, idempotent: false }),
});

test("the create envelope is compact, create-only, and carries the user's words", () => {
  const envelope = buildStmNoteCreateEnvelope({
    writeId: WRITE_ID,
    accountEpoch: 7,
    recordId: WRITE_ID,
    text: FACT,
    clientWriteRef: null,
  });
  assert.ok(envelope);
  assert.deepEqual(Object.keys(envelope), ["write_id", "account_epoch", "domain", "op"]);
  assert.deepEqual(Object.keys(envelope.op), ["op", "record_id", "content"]);
  assert.deepEqual(Object.keys(envelope.op.content), ["text", "client_write_ref"]);
  assert.equal(envelope.domain, "stm-notes");
  assert.equal(envelope.op.op, "create");
  assert.equal(envelope.op.content.text, FACT);
  assert.equal(envelope.account_epoch, 7);
  assert.match(envelope.write_id, WRITE_ID_PATTERN);
  assert.equal(JSON.stringify(JSON.parse(JSON.stringify(envelope))), JSON.stringify(envelope));
  assert.equal(buildStmNoteCreateEnvelope({
    writeId: WRITE_ID,
    accountEpoch: 7,
    recordId: WRITE_ID,
    text: "",
    clientWriteRef: null,
  }), null);
  // red-proof: allowing `op: "patch"` here would reintroduce the retired edit
  // door on a path that is create-only by ruling.
});

test("sendUserAssertedStmNote posts the fact to /v1/stm-notes/ops", async () => {
  const http = new ScriptedHttp();
  http.respond(accepted(WRITE_ID));
  const result = await sendUserAssertedStmNote(http, {
    text: FACT,
    accountEpoch: 7,
    entropy: ENTROPY,
    clientWriteRef: null,
  });
  assert.equal(result.ok, true);
  assert.equal(http.calls.length, 1);
  assert.equal(http.calls[0]!.method, "POST");
  assert.equal(http.calls[0]!.path, STM_NOTES_OPS_PATH);
  const envelope = http.calls[0]!.body as {
    domain: string;
    account_epoch: number;
    op: { op: string; content: { text: string } };
  };
  assert.equal(envelope.domain, "stm-notes");
  assert.equal(envelope.account_epoch, 7);
  assert.equal(envelope.op.op, "create");
  assert.equal(envelope.op.content.text, FACT);
});

test("a 422 invalid_envelope is a failure, not a silent drop of the user's words", async () => {
  const http = new ScriptedHttp();
  http.respond({
    status: WRITE_ERRORS.validation.status,
    json: JSON.parse(WRITE_ERRORS.validation.body),
    text: WRITE_ERRORS.validation.body,
  });
  const result = await sendUserAssertedStmNote(http, {
    text: FACT,
    accountEpoch: 7,
    entropy: ENTROPY,
  });
  assert.equal(result.ok, false);
});

test("observeAccountEpochFromTasksRead never stamps zero from a missing field", async () => {
  const http = new ScriptedHttp();
  http.respond({
    status: 200,
    json: { contractVersion: "0.6.0", items: [], window: {}, completeness: {}, absence: {} },
    text: "{}",
  });
  const epochs = createDevAccountEpochProvider();
  const observed = await observeAccountEpochFromTasksRead(http, epochs);
  assert.equal(observed, null);
  assert.equal(epochs.currentAccountEpoch(), null);
  assert.equal(http.calls[0]!.method, "GET");
  assert.equal(http.calls[0]!.path, "/v1/tasks?limit=1");
});

test("observeAccountEpochFromTasksRead records a real tasks-read epoch", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: { accountEpoch: 7 }, text: '{"accountEpoch":7}' });
  const epochs = createDevAccountEpochProvider();
  assert.equal(await observeAccountEpochFromTasksRead(http, epochs), 7);
});

test("MemoryCorrectionStore submits the fact and does not invent an epoch", async () => {
  const http = new ScriptedHttp();
  http.respond(accepted(WRITE_ID));
  const store = MemoryCorrectionStore.open(
    http,
    createDevAccountEpochProvider(7),
    () => ENTROPY,
  );
  await store.submitFact(`  ${FACT}  `);
  const envelope = http.calls[0]!.body as { op: { content: { text: string } } };
  assert.equal(envelope.op.content.text, FACT);
  await assert.rejects(() => store.submitFact("   "), /empty fact/);
});

test("MemoryCorrectionStore refuses to stamp a fact without an account epoch", async () => {
  const http = new ScriptedHttp();
  http.respond({ status: 200, json: { items: [] }, text: "{}" });
  const store = MemoryCorrectionStore.open(
    http,
    createDevAccountEpochProvider(null),
    () => ENTROPY,
  );
  await assert.rejects(() => store.submitFact(FACT), /account epoch/);
  assert.equal(http.calls.some((call) => call.method === "POST"), false);
});
