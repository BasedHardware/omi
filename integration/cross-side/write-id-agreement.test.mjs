/**
 * CROSS-SIDE: the client's journaled `write_id` IS the server's row.
 *
 * ── WHAT THIS ANSWERS THAT NOTHING ELSE DOES ───────────────────────────────
 *
 * The client suite proves the outbox stamps a write id at enqueue and puts it
 * on the wire. The server suite proves the door records what it was sent. Both
 * are green today and neither can see the thing that actually matters: that the
 * id the CLIENT wrote into its journal is the id the SERVER filed the row
 * under. Each side tests against its own idea of the other's wire — the exact
 * shape `wire-agreement.test.mjs` was built for, applied to the write path.
 *
 * The stake is concrete. `write_id` is the idempotency key for the whole write
 * wire (COORD-write-path-rulings B1). If the two sides ever disagree about it —
 * a hex-case difference, a re-mint at send, a truncation — nothing fails
 * loudly. Replays stop deduping, and a crash-replayed op applies twice. That is
 * a silent double-write of a user's edit, discovered later, in data.
 *
 * ── HOW IT IS JOINED (swarm-protocol §5) ───────────────────────────────────
 *
 * Producer side: the server's own run-scoped tally at
 * `/v1/qa/control/stats?run=<id>`, keyed by the `x-omi-run-id` header this
 * test's transport binding sets. Consumer side: the client's journal, read
 * through `Outbox.pendingOps()` before the drain — the value the outbox
 * actually wrote, not one this test computed.
 *
 * Both sides are run here, by one agent, against one live process. No number
 * from the dispatch side appears in a verdict: "the client sent a write id" is
 * never evidence that the server filed one, so every assertion below reads the
 * server's own record.
 *
 * The exact-equality assertion uses the STRAGGLER export, because that is the
 * one server surface that returns a `write_id` verbatim. A stale-epoch refusal
 * preserves the full envelope (B3), so the row it writes carries the id the
 * client minted — and comparing those two strings is the whole point of this
 * file.
 *
 * ── WHY THIS IS NOT IN `core/` ─────────────────────────────────────────────
 *
 * Same reason as its sibling: core isolation rule 3 forbids `fetch` against
 * backend endpoint shapes outside adapters and shells, and an end-to-end driver
 * must do exactly that. The client half is imported from the BUILT dist — the
 * same module the surfaces call, never a re-implementation.
 */

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { after, before, describe, test } from "node:test";

const client = await import(
  new URL("../../core/packages/adapters-platform/dist/index.js", import.meta.url).href
);
const sync = await import(new URL("../../core/packages/sync/dist/index.js", import.meta.url).href);
const { REPO_PATHS } = await import(new URL("../lib/provenance.mjs", import.meta.url).href);

const PLATFORM_REPO = REPO_PATHS.platform;
const BOOT_TIMEOUT_MS = 20_000;
const RUN_ID_HEADER = "x-omi-run-id";
const ACTIVE_EPOCH = 7;
const STALE_EPOCH = 3;

let child;
let baseUrl;
let devToken;

/**
 * Readiness comes from the CHILD's own announcement, never from a port probe.
 * A probe that accepts any 200 cannot tell "my server is up" from "someone
 * else's server is up", and this harness runs concurrently with five other
 * lanes.
 */
before(async () => {
  child = spawn("bun", ["run", "integration/control/live-service.ts"], {
    cwd: PLATFORM_REPO,
    env: { ...process.env, TZ: "UTC" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let banner = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => { banner += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });

  const deadline = Date.now() + BOOT_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`live-service exited before readiness (${child.exitCode}): ${stderr}${banner}`);
    }
    const line = banner.split("\n").find((entry) => entry.includes("live_service_listening"));
    if (line !== undefined) {
      const announced = JSON.parse(line);
      const probe = await fetch(`${announced.url}/health`).catch(() => null);
      if (probe?.ok === true) {
        baseUrl = announced.url;
        devToken = announced.devToken;
        return;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`live-service did not become ready. stdout:\n${banner}\nstderr:\n${stderr}`);
});

after(async () => {
  if (child && child.exitCode === null) child.kill();
});

const control = async (path, body) => {
  const response = await fetch(`${baseUrl}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { authorization: `Bearer ${devToken}`, "content-type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) throw new Error(`control ${path} -> ${response.status}`);
  return response.json();
};

/** ADR-010 §1's forward activation order, so the fence admits this account. */
const cutOverLive = async () => {
  const observe = (overrides) => control("/v1/qa/control/observe", {
    control_revision: 1,
    account_generation: "legacy",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
    ...overrides,
  });
  await control("/v1/qa/control/reset", {});
  await observe({});
  await observe({ control_revision: 2, account_generation: "migrating" });
  await observe({ control_revision: 3, account_generation: "new", account_epoch: ACTIVE_EPOCH });
  await control("/v1/qa/control/activate", { epoch: ACTIVE_EPOCH, at_control_revision: 3 });
};

/**
 * The transport binding. It owns the base URL, the bearer token and the run-id
 * header — ADR-008 §3, and the reason the adapter package never sees any of
 * them. It hands the adapter the RAW body text, which is not a nicety: two
 * refusal classes share HTTP 409 and are told apart by bytes, so a binding that
 * supplies only parsed JSON makes a straggler look like a conflict.
 */
const httpFor = (runId) => ({
  async request(method, path, body) {
    const response = await fetch(`${baseUrl}${path}`, {
      method,
      headers: {
        authorization: `Bearer ${devToken}`,
        [RUN_ID_HEADER]: runId,
        ...(body === undefined ? {} : { "content-type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const text = await response.text();
    let json = null;
    try { json = JSON.parse(text); } catch { json = null; }
    return { status: response.status, json, text };
  },
});

/** In-memory durable bridge — the shape a shell binds, small enough to inline. */
const memoryBridge = () => {
  const logs = new Map();
  const kvs = new Map();
  return {
    uid: "cross-side",
    generation: 1,
    async openLog(name) {
      if (!logs.has(name)) logs.set(name, { lsn: 0, entries: [] });
      const log = logs.get(name);
      return {
        append: async (payload) => { log.lsn += 1; log.entries.push({ lsn: log.lsn, payload }); return log.lsn; },
        scan: async (after_) => log.entries.filter((entry) => entry.lsn > after_),
        truncate: async (upTo) => { log.entries = log.entries.filter((entry) => entry.lsn > upTo); },
      };
    },
    async openKv(name) {
      if (!kvs.has(name)) kvs.set(name, new Map());
      const kv = kvs.get(name);
      return {
        get: async (key) => kv.get(key) ?? null,
        set: async (key, value) => void kv.set(key, value),
        delete: async (key) => void kv.delete(key),
      };
    },
    async destroyAll() { logs.clear(); kvs.clear(); },
  };
};

const realEnv = () => ({
  now: () => Date.now(),
  random: () => Math.random(),
  delay: (ms, fn) => { const t = setTimeout(fn, ms); return () => clearTimeout(t); },
  fallbackSink: { records: [], record(event) { this.records.push(event); } },
});

/** Distinct 32-byte reads. The shell owns entropy; the contract refuses a short read. */
const entropySource = () => {
  let counter = 0;
  return () => {
    counter += 1;
    const bytes = new Uint8Array(32);
    for (let i = 0; i < 32; i += 1) bytes[i] = (counter * 31 + i) & 0xff;
    return bytes;
  };
};

const openOutbox = async (runId, epoch) => {
  const env = realEnv();
  const box = await sync.Outbox.open(
    memoryBridge(),
    env,
    client.platformTasksTransport({
      http: httpFor(runId),
      onControlUnavailable: () => {},
    }),
    "tasks",
    client.createPlatformWriteStamps({
      entropy: entropySource(),
      epochs: client.createDevAccountEpochProvider(epoch),
    }),
  );
  return { box, env };
};

const pendingOp = (opId, description) => ({
  opId,
  domain: "tasks",
  recordId: "task-fixture-1",
  payload: JSON.stringify({ op: "patch", opId, id: "task-fixture-1", at: 1_000, patch: { description } }),
  summary: `Edit task task-fixture-1: description`,
  attempts: 0,
});

/** Drain until the op reaches a terminal outcome or the budget expires. */
const drain = async (box) => {
  for (let i = 0; i < 60 && box.pendingOps().length > 0; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
};

describe("the real write client against the real write door", () => {
  test("an applied op: the server files the id the client journaled, joined by run id", async () => {
    await cutOverLive();
    const runId = `client-applied-${crypto.randomUUID()}`;
    const { box } = await openOutbox(runId, ACTIVE_EPOCH);

    await box.enqueue(pendingOp("op-applied", "buy oat milk"));

    // THE CONSUMER-SIDE VALUE, read out of the journal rather than computed
    // here. If this test minted its own id it would prove only that this test
    // can do arithmetic.
    const journaled = box.pendingOps()[0];
    assert.ok(journaled, "the op is journaled before it is sent");
    const journaledWriteId = journaled.writeId;
    assert.match(journaledWriteId, /^[0-9a-f]{64}$/, "B1: 64 lowercase hex, minted at enqueue");
    assert.equal(journaled.accountEpoch, ACTIVE_EPOCH, "the epoch the op was created under is journaled with it");

    await drain(box);

    // THE PRODUCER-SIDE COUNTER, from the server, scoped to this run.
    const stats = await control(`/v1/qa/control/stats?run=${encodeURIComponent(runId)}`);
    assert.equal(stats.run, runId, "the tally is the one this run produced");
    assert.equal(
      stats.writeOps.outcomes.accepted,
      1,
      `the server recorded exactly one accept for this run: ${JSON.stringify(stats.writeOps)}`,
    );
    // Not idempotent: this is the FIRST time the server has seen this id. The
    // distinction matters — `accepted_idempotent` is the registry answering
    // from a recorded outcome, which is a different fact about a different op.
    assert.equal(stats.writeOps.outcomes.accepted_idempotent, 0);
    assert.equal(stats.writeOps.outcomes.stale_epoch, 0, "a current epoch is not a straggler");
    assert.equal(stats.writeOps.preservedEnvelopes, 0, "an accepted op preserves nothing");

    // AND the consumer-side observation that the record is really there. A
    // door's own 200 is a dispatch-side number; the store is the answer.
    const stored = await control("/v1/qa/control/tasks");
    assert.ok(
      stored.records.some((row) => row.record_id === "task-fixture-1"),
      "the record the door said it applied is in the store",
    );
    assert.deepEqual(await box.deadLetters(), [], "an applied op is never a dead letter");
    assert.equal(box.pendingOps().length, 0, "and it left the queue confirmed");
  });

  test("a straggler: the preserved row's write_id EQUALS the client's journaled one", async () => {
    await cutOverLive();
    const runId = `client-straggler-${crypto.randomUUID()}`;
    // The client believes it is on a superseded generation — exactly the
    // straggler the fence exists to refuse, and the only case that preserves a
    // full envelope server-side (B3), which is what makes the ids comparable.
    const { box } = await openOutbox(runId, STALE_EPOCH);

    await box.enqueue(pendingOp("op-straggler", "pay the water bill"));
    const journaledWriteId = box.pendingOps()[0].writeId;
    assert.match(journaledWriteId, /^[0-9a-f]{64}$/);

    await drain(box);

    // Client side: the op is dead, with David's stale-epoch reason and the full
    // payload the signed copy promises is "saved below".
    const dead = await box.deadLetters();
    assert.equal(dead.length, 1, "the refusal produced exactly one dead letter");
    assert.equal(dead[0].failure.reason, "stale_epoch", "B2: never conflict, never gone");
    assert.equal(
      JSON.parse(dead[0].payload).patch.description,
      "pay the water bill",
      "the user's actual edit is retained, not a summary of it",
    );

    // Server side: the preserved envelope, from the server's own export.
    const exported = await control("/v1/qa/control/stragglers");
    assert.equal(exported.preserved.length, 1, "the fence preserved exactly one envelope");

    // THE ASSERTION THIS FILE EXISTS FOR. One string, written by the client
    // into its journal; one string, written by the server into its row. If
    // these ever diverge, replays stop deduping and a crash-replayed edit
    // applies twice — silently, in data, discovered much later.
    assert.equal(
      exported.preserved[0].write_id,
      journaledWriteId,
      "the server's row is filed under the id the client journaled",
    );
    assert.equal(
      exported.preserved[0].account_epoch,
      STALE_EPOCH,
      "and under the epoch the op was created under, not the one that is current",
    );
    // The envelope round-trips whole: an operator reconstructing this edit by
    // hand needs the patch, not a reference to it.
    assert.equal(
      JSON.parse(exported.preserved[0].envelope_json).op.patch.description,
      "pay the water bill",
    );

    const stats = await control(`/v1/qa/control/stats?run=${encodeURIComponent(runId)}`);
    assert.match(
      JSON.stringify(stats.fence) + JSON.stringify(stats.writeOps),
      /stale_epoch|request_epoch_behind/,
      "the server counted this run's refusal as a stale epoch",
    );
  });
});
