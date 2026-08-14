// LIFECYCLE: permanent
//
// STAGE (c) OF THE L3 WRITE JOURNEY — the client OUTBOX draining through the
// registered write door, over real HTTP.
//
// ── WHY THIS IS A DIFFERENT CLAIM FROM STAGE (b) ────────────────────────────
//
// Stage (b) proves the DOOR: a driver that builds an envelope with the shipped
// adapter and sends it gets an apply, an idempotent replay and a stale-epoch
// refusal, and the server's own counters agree. That is a true statement about
// the server and a weaker one about the product, because the thing that will
// actually send ops in the app is not a driver — it is `Outbox`, with its
// journal, its stamping, its retry state machine and its dead-letter store.
//
// Every one of those is a place the write path can break in a way stage (b)
// cannot see. The two failures this stage exists for, both named in B1:
//
//   1. A write id minted at SEND time instead of at enqueue. Stage (b) never
//      sees it, because a driver sends each envelope once. An outbox replaying
//      after a crash mints a new id, the server registry does not recognise the
//      retry, and the op applies twice.
//   2. An account epoch re-stamped at send time with whatever is current. An op
//      authored in a superseded generation then quietly applies in the new one
//      — precisely the straggler the fence exists to catch, walking straight
//      past it.
//
// So this drives the REAL `Outbox` from `@omi-core/sync`, with the REAL
// transport (`platformTasksTransport`), the REAL stamp source and the REAL dev
// epoch provider, over an HTTP client that actually talks to the door. Nothing
// is scripted. The only fakes are the durable bridge and the clock, which are
// the testkit's own (`MemoryStore`, `ManualEnv`) and are what make a drain
// deterministic rather than a sleep.
//
// ── THE JOIN ────────────────────────────────────────────────────────────────
//
// Every request this outbox makes carries `x-omi-run-id`, so the server's fence
// and write-ops counters can be read back for THIS drain and nobody else's. The
// client-side numbers — what the journal holds, what the dead-letter store
// holds — are the consumer side. Neither is allowed to stand alone.

// NOT from `write-journey.mjs`: that module runs its CLI at import time, and
// importing a constant from it created a top-level-await cycle that exited 13
// with no verdict. See `write-journey-protocol.mjs`.
import { RUN_ID_HEADER } from "./write-journey-protocol.mjs";
import { createReadableTaskBag } from "./write-journey-task.mjs";

/**
 * A real `HttpClient` over `fetch`, scoped to one door and one run id.
 *
 * `text` is supplied and that is LOAD-BEARING, not plumbing: `stale_epoch` and
 * `conflict` are both 409 and are distinguished by body bytes, never by status.
 * A client that drops the body makes the op-sender unable to tell a superseded
 * generation from a genuine concurrent edit, and the user is told their saved
 * edit conflicted when it did not.
 */
export function liveHttpClient({ baseUrl, token, runId, fetchImpl = fetch }) {
  const calls = [];
  return {
    calls,
    async request(method, path, body) {
      const response = await fetchImpl(`${baseUrl}${path}`, {
        method,
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${token}`,
          [RUN_ID_HEADER]: runId,
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      const text = await response.text();
      // The BODY is recorded, not just the status. `stale_epoch` and `conflict`
      // are both 409 and differ only in bytes, so a call log that keeps only
      // the status cannot tell a verdict which one happened.
      calls.push({ method, path, body, status: response.status, text });
      return { status: response.status, text };
    },
  };
}

/**
 * Drive the outbox. Returns FACTS; grades nothing (same split as the rest of
 * this journey, for the same reason).
 *
 * `deps` are the BUILT client modules, injected rather than imported here so
 * the verdict tests can run without a dist.
 */
export async function runOutboxDrain(options) {
  const {
    doorUrl, token, runId, activeEpoch, accountId,
    buildEnvelope,
    deps: { MemoryStore, ManualEnv, Outbox, platformTasksTransport, createPlatformWriteStamps, createDevAccountEpochProvider },
    fetchImpl = fetch,
  } = options;

  const drainRunId = `${runId}-outbox`;
  const staleRunId = `${runId}-outbox-stale`;
  const controlRefreshes = [];

  // The http client is returned alongside the box: its call log is the only
  // record of the BYTES the outbox exchanged, and a verdict that cannot see
  // them is back to distinguishing two 409 classes by status.
  const openBox = async ({ epoch, runIdForHttp, store, env }) => {
    const http = liveHttpClient({ baseUrl: doorUrl, token, runId: runIdForHttp, fetchImpl });
    const box = await Outbox.open(
      store.openBridge(accountId),
      env,
      platformTasksTransport({
        http,
        // W1: `control_unavailable` is backpressure — refresh control state and
        // drain where authority lives. Never retry-in-place, never a dead
        // letter. Recorded so a run can say whether it happened.
        onControlUnavailable: (op) => controlRefreshes.push(op.opId),
      }),
      "tasks",
      createPlatformWriteStamps({
        entropy: () => crypto.getRandomValues(new Uint8Array(32)),
        epochs: createDevAccountEpochProvider(epoch),
      }),
    );
    return { box, http };
  };

  // The journaled payload is the CLIENT's own domain op (`TaskOp`), not the
  // wire op. `taskOpToWriteOp` is the one place that mapping lives, and driving
  // the outbox with a pre-mapped wire op would route around the very seam this
  // stage exists to exercise — the op would still send, and the mapping would
  // be untested while looking tested.
  /**
   * A REAL round trip does not settle inside one `advance`.
   *
   * `ManualEnv.advance` fires the timers that are due when it is called. With a
   * scripted transport every send resolves synchronously, so one advance drains
   * a whole retry ladder and the hermetic tests can say `advance(700_000)`.
   * Over real HTTP the next timer is only scheduled after the previous send's
   * promise settles, so a single advance fires one step and returns — and the
   * op that has not been retried yet looks exactly like an op the outbox
   * dropped. That misreading cost this stage two false reds.
   *
   * So: advance in steps, yielding to the event loop between them, until the
   * caller's condition holds or the bound is hit. The number of steps taken is
   * returned as a FACT rather than hidden, because "it needed 9 rounds" and "it
   * needed 1" are different things to know about a retry ladder.
   */
  const drainUntil = async (env, done, { step = 60_000, bound = 60 } = {}) => {
    for (let rounds = 0; rounds < bound; rounds += 1) {
      if (await done()) return { settled: true, rounds };
      await env.advance(step);
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    return { settled: await done(), rounds: bound };
  };

  const recordId = options.recordId ?? "flying-dragon-vibrant";
  const seedWriteId = Array.from(crypto.getRandomValues(new Uint8Array(32)), (byte) =>
    byte.toString(16).padStart(2, "0")).join("");
  const seedBuilt = buildEnvelope({
    domain: "tasks",
    writeId: seedWriteId,
    op: {
      op: "create",
      record_id: recordId,
      content: createReadableTaskBag({ description: "seeded for the outbox", completed: false }),
    },
  }, activeEpoch);
  if (!seedBuilt.ok) {
    throw new Error(`the shipped adapter refused the outbox seed: ${JSON.stringify(seedBuilt)}`);
  }
  const seedResponse = await fetchImpl(`${doorUrl}${seedBuilt.path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
      [RUN_ID_HEADER]: `${runId}-outbox-seed`,
    },
    body: JSON.stringify(seedBuilt.envelope),
  });
  const seed = { status: seedResponse.status, text: await seedResponse.text() };
  if (seed.status !== 200) {
    throw new Error(`the conformant outbox seed was not applied: ${seed.status} ${seed.text}`);
  }
  const op = (opId) => ({
    opId,
    domain: "tasks",
    recordId,
    payload: JSON.stringify({
      op: "patch", opId, id: recordId, at: 1_000,
      patch: { description: "drained by the outbox" },
    }),
    summary: `Edit task ${recordId}: description`,
    attempts: 0,
  });

  // ── the happy drain, at the ACTIVE epoch ─────────────────────────────────
  const store = new MemoryStore();
  const env = new ManualEnv();
  const { box, http: http1 } = await openBox({ epoch: activeEpoch, runIdForHttp: drainRunId, store, env });
  const http1PostCount = () => http1.calls.filter((c) => c.method === "POST").length;
  await box.enqueue(op("outbox-op-1"));
  const drained = await drainUntil(env, async () => http1PostCount() > 0);
  const journaled = await readJournal(store, accountId);
  const deadAfterDrain = await box.deadLetters();

  // ── B1's replay, WITHOUT handing the outbox a stamp ─────────────────────
  //
  // This used to open a second Outbox and enqueue the same op with the
  // journaled `writeId`/`accountEpoch` supplied by hand. `41de6e8859` closed
  // that door: the outbox mints the stamps and REFUSES an op that arrives
  // carrying them, which is the right reading of B1 — a caller that can supply
  // a write id is a caller that can supply a fresh one on every replay, which
  // is the defect B1 exists to prevent. The old construction was simulating a
  // replay through an API that must not be able to express one.
  //
  // So the replay is sent the way a replay actually reaches the server — the
  // identical bytes the outbox itself put on the wire, resent — and the claim
  // it establishes is unchanged and slightly stronger: the server's registry
  // recognises the id the CLIENT journaled. The outbox is not asked to do
  // something it now correctly refuses.
  const drainWire = http1.calls.filter((c) => c.method === "POST").at(-1) ?? null;
  let replayResponse = null;
  if (drainWire !== null) {
    const again = await fetchImpl(`${doorUrl}${drainWire.path}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${token}`,
        [RUN_ID_HEADER]: drainRunId,
      },
      body: JSON.stringify(drainWire.body),
    });
    replayResponse = { status: again.status, text: await again.text() };
  }

  // ── the straggler: an op authored under a SUPERSEDED epoch ───────────────
  // The client's epoch provider is behind. Nothing about the op is otherwise
  // different, and nothing in the client decides it is stale — the fence does.
  const staleStore = new MemoryStore();
  const staleEnv = new ManualEnv();
  const { box: staleBox, http: staleHttp } = await openBox({ epoch: activeEpoch - 1, runIdForHttp: staleRunId, store: staleStore, env: staleEnv });
  await staleBox.enqueue(op("outbox-op-stale"));
  const stalled = await drainUntil(staleEnv, async () => (await staleBox.deadLetters()).length > 0);
  const deadLetters = await staleBox.deadLetters();
  // The straggler's OWN journal row, read back out of its durable log. The
  // drain box's journal says nothing about what the straggler was stamped with.
  const staleJournaled = await readJournal(staleStore, accountId);

  return {
    drainRunId,
    staleRunId,
    recordId,
    seed,
    journaled,
    staleJournaled,
    epoch: { active: activeEpoch, straggler: activeEpoch - 1 },
    deadAfterDrain,
    deadLetters,
    controlRefreshes,
    rounds: { drain: drained, stale: stalled },
    drainWire,
    replayResponse,
    // The straggler's own socket: the envelope bytes that left the client and
    // the refusal bytes that came back. Asserted by
    // `straggler_wire_matches_its_journal` — see that row for why neither the
    // dead letter nor the fence tally can stand in for this.
    staleResponse: (staleHttp.calls.filter((c) => c.method === "POST").at(-1) ?? null),
  };
}

/**
 * What the CLIENT actually wrote to its journal, read back out of the durable
 * log rather than out of the object we handed in. An op the caller stamped and
 * an op the journal holds are different things, and B1 is a claim about the
 * second one.
 */
async function readJournal(store, accountId) {
  const bridge = store.openBridge(accountId);
  const log = await bridge.openLog("outbox-tasks");
  const entries = await log.scan(0);
  const ops = entries
    .map((e) => JSON.parse(e.payload))
    .filter((e) => e.t === "op")
    .map((e) => e.op);
  const first = ops[0] ?? null;
  return {
    count: ops.length,
    writeId: first?.writeId ?? null,
    accountEpoch: first?.accountEpoch ?? null,
    opId: first?.opId ?? null,
  };
}

const pass = (detail) => ({ result: "pass", detail });
const fail = (detail) => ({ result: "fail", detail });

/**
 * The stage-(c) assertions. Registry, not conditionals — same reason as
 * everywhere else in this harness.
 */
export const OUTBOX_ASSERTIONS = [
  {
    name: "outbox_drained_to_the_door",
    claim: "the client outbox's enqueued op reached the registered write door and was applied",
    measuredBy: "server: the route's own accepted count for the outbox's run id",
    corroboratedBy: "client: the outbox holds no dead letter for that op, and its journal holds exactly one",
    evaluate: (o, { producer }) => {
      const writeOps = producer.drain.writeOps;
      if (writeOps === null) {
        return fail(`the server recorded NO write outcome for run ${o.drainRunId} — the outbox sent nothing, or the run-id join is broken (null, not zero)`);
      }
      if (o.journaled.count !== 1) {
        return fail(`the client journal holds ${o.journaled.count} op(s); this drain enqueued one`);
      }
      const accepted = writeOps.outcomes.accepted + writeOps.outcomes.accepted_idempotent;
      if (accepted < 1) {
        return fail(`the server accepted ${accepted} op(s) from the outbox's run — the drain reached the door and was refused, or never reached it`);
      }
      if (o.deadAfterDrain.length !== 0) {
        return fail(`the outbox dead-lettered ${o.deadAfterDrain.length} op(s) on a drain the server says it accepted — the two sides disagree about the same op`);
      }
      return pass(`server recorded accepted=${writeOps.outcomes.accepted} accepted_idempotent=${writeOps.outcomes.accepted_idempotent} for run ${o.drainRunId}; client journal holds 1 op and 0 dead letters`);
    },
  },
  {
    name: "journaled_write_id_is_the_one_the_server_registered",
    claim: "the write id the CLIENT journaled at enqueue is the one the server's registry recognises on replay",
    measuredBy: "client: the write_id read back out of the durable journal",
    corroboratedBy: "server: replaying that same id returns idempotent=true, which only a registry row for it can produce",
    evaluate: (o, { producer }) => {
      const replayResponse = o.replayResponse;
      if (o.journaled.writeId === null) {
        return fail("the client journaled no write id — B1 requires it minted at enqueue and journaled WITH the op");
      }
      if (!/^[0-9a-f]{64}$/.test(o.journaled.writeId)) {
        return fail(`the journaled write id is not 64 lowercase hex: ${o.journaled.writeId}`);
      }
      if (o.journaled.accountEpoch === null) {
        return fail("the client journaled no account epoch — the straggler stamp the fence compares against is missing");
      }
      if (o.drainWire === null || typeof o.drainWire.body !== "object" || o.drainWire.body === null) {
        return fail("the outbox put no readable envelope on the wire, so nothing links its journal to the server");
      }
      // The journal and the WIRE, before the server is consulted at all. B1's
      // other named failure is an epoch re-stamped at send time, and no
      // server-side answer can see it.
      if (o.drainWire.body.write_id !== o.journaled.writeId) {
        return fail(
          `the journal holds write id ${String(o.journaled.writeId).slice(0, 12)}… and the outbox sent`
          + ` ${String(o.drainWire.body.write_id).slice(0, 12)}… — a stamp minted at send time`,
        );
      }
      if (o.drainWire.body.account_epoch !== o.journaled.accountEpoch) {
        return fail(
          `the journal holds account_epoch ${o.journaled.accountEpoch} and the outbox sent`
          + ` ${o.drainWire.body.account_epoch} — re-stamping at send time makes an op authored in a`
          + " superseded generation apply in the new one",
        );
      }
      if (replayResponse === null) {
        return fail("the replay never reached the door, so nothing establishes that the server knows this write id");
      }
      let body;
      try {
        body = JSON.parse(replayResponse.text);
      } catch {
        return fail(`the replay response is not JSON: ${replayResponse.text.slice(0, 120)}`);
      }
      if (body.idempotent !== true) {
        return fail(
          `replaying the CLIENT-journaled write id ${o.journaled.writeId.slice(0, 12)}… returned idempotent=${JSON.stringify(body.idempotent)}.`
          + " The server did not recognise an id the client had already used, which is what a send-time mint looks like from the outside:"
          + " the op applies twice and the user's edit is duplicated.",
        );
      }
      const total = producer.drain.writeOps?.outcomes.accepted_idempotent ?? 0;
      if (total < 1) {
        return fail(`the wire said idempotent=true but the server recorded ${total} idempotent outcome(s) — the flag and the record disagree`);
      }
      return pass(`client journaled ${o.journaled.writeId.slice(0, 12)}… at epoch ${o.journaled.accountEpoch}; the server answered that same id idempotent=true and recorded it`);
    },
  },
  {
    name: "straggler_dead_letters_as_stale_epoch",
    claim: "an op the outbox authored under a superseded epoch is refused by the fence and dead-lettered as stale_epoch — never as a conflict, and never silently dropped",
    measuredBy: "server: the fence's stale_epoch and preservedEnvelopes counts for the straggler's run id",
    corroboratedBy: "client: the outbox's own dead-letter store, holding that op with the stale_epoch reason",
    evaluate: (o, { producer }) => {
      const fence = producer.stale.fence;
      if (fence === null) {
        return fail(`the fence recorded no decision for run ${o.staleRunId} — the straggler never reached the fence`);
      }
      if (fence.refused.stale_epoch !== 1) {
        return fail(`the fence refused ${fence.refused.stale_epoch} stale op(s) for this run; the outbox sent one`);
      }
      if (fence.preservedEnvelopes !== 1) {
        return fail(
          `the fence preserved ${fence.preservedEnvelopes} envelope(s) for the straggler.`
          + " A straggler refused and not preserved is a silently lost edit.",
        );
      }
      if (o.deadLetters.length !== 1) {
        return fail(
          `the server refused one straggler and the client holds ${o.deadLetters.length} dead letter(s).`
          + " An op refused server-side and dropped client-side is a user's edit that vanished with no surface to recover it from.",
        );
      }
      const letter = o.deadLetters[0];
      const reason = letter.failure?.reason ?? letter.reason ?? null;
      if (reason !== "stale_epoch") {
        return fail(
          `the client dead-lettered the straggler as ${JSON.stringify(reason)}.`
          + " B2 rules out `conflict` by name: telling a person their saved edit conflicted, when the server refused an op"
          + " authored in a superseded generation, is a false report about their own content.",
        );
      }
      if (o.controlRefreshes.length !== 0) {
        return fail(`the straggler triggered ${o.controlRefreshes.length} control refresh(es) — stale_epoch is not backpressure and must not be handled as W1's availability signal`);
      }
      return pass(`fence refused stale_epoch=1 and preserved 1 envelope for run ${o.staleRunId}; the client holds exactly 1 dead letter, reason stale_epoch`);
    },
  },
  {
    /**
     * WHY THIS EXISTS WHEN THE FENCE TALLY AND THE DEAD LETTER ALREADY AGREE.
     *
     * Those two are the server's DECISION and the client's CLASSIFICATION. The
     * bytes on the straggler's own socket are neither, and they carry the one
     * thing this stage's own module header claims to catch and — until this row
     * — did not actually check: that the envelope the outbox PUT ON THE WIRE
     * carries the write id and account epoch its journal holds.
     *
     * B1 is explicit that the account epoch is the epoch the op was AUTHORED
     * under, journaled with it, and never re-stamped at send time — because an
     * op re-stamped with whatever is current applies in the generation it was
     * not authored for, which is exactly the straggler the fence cannot catch.
     * A transport that dropped, defaulted or rewrote the field would still
     * produce a `stale_epoch` refusal here (the provider is behind either way),
     * a preserved envelope, and a correct dead letter. All three existing
     * arbiters would agree, and the field would be wrong.
     *
     * It also pins the refusal BYTES the client's transport actually received,
     * rather than trusting that the classification came from the right input:
     * `sendPlatformTaskOp` calls the `text` requirement load-bearing because
     * `stale_epoch` and `conflict` are both 409 and differ only in the body.
     */
    name: "straggler_wire_matches_its_journal",
    claim: "the envelope the outbox actually sent carries the write id and the superseded account epoch its own journal holds, and the refusal it received is the ratified stale_epoch body",
    measuredBy: "client: the straggler's row in the durable journal",
    corroboratedBy: "wire: the request and response bytes on the straggler's own socket, against the vendored corpus row",
    evaluate: (o, { corpus }) => {
      const wire = o.staleResponse;
      if (wire === null) {
        return fail(
          "the straggler never reached the wire at all. The fence tally and the dead letter below can both be"
          + " satisfied by a run in which nothing was sent, so this is the row that says the op left the client.",
        );
      }
      const envelope = wire.body ?? null;
      if (envelope === null || typeof envelope !== "object") {
        return fail(`the outbox sent no readable envelope: ${JSON.stringify(envelope)}`);
      }
      const journaled = o.staleJournaled;
      if (journaled.writeId === null || journaled.accountEpoch === null) {
        return fail(`the straggler was journaled without a stamp (write_id=${journaled.writeId}, account_epoch=${journaled.accountEpoch})`);
      }
      if (envelope.write_id !== journaled.writeId) {
        return fail(
          `the journal holds write id ${String(journaled.writeId).slice(0, 12)}… and the wire carried`
          + ` ${String(envelope.write_id).slice(0, 12)}… — an id minted at send time is a replay the registry cannot recognise`,
        );
      }
      if (envelope.account_epoch !== journaled.accountEpoch) {
        return fail(
          `the journal holds account_epoch ${journaled.accountEpoch} and the wire carried ${envelope.account_epoch}.`
          + " B1: the epoch is the one the op was AUTHORED under. Re-stamping at send time makes an op authored in a"
          + " superseded generation apply in the new one — the straggler the fence exists to catch, walking past it.",
        );
      }
      if (!(envelope.account_epoch < o.epoch.active)) {
        return fail(
          `the straggler carried account_epoch ${envelope.account_epoch} and the active epoch is ${o.epoch.active}.`
          + " It is not superseded, so the refusal below proves nothing about stragglers.",
        );
      }
      const row = corpus.byOutcome.get("stale_epoch");
      if (row === undefined) return fail("the vendored corpus has no stale_epoch row — there is no arbiter for these bytes");
      if (wire.status !== row.status || wire.text !== row.body) {
        return fail(
          `the bytes the outbox's transport received are not the ratified refusal.\n    wire:   ${wire.status} ${wire.text}`
          + `\n    corpus: ${row.status} ${row.body}`,
        );
      }
      return pass(
        `the outbox sent write_id ${String(envelope.write_id).slice(0, 12)}… at account_epoch ${envelope.account_epoch}`
        + ` (< active ${o.epoch.active}), exactly as journaled, and received the corpus-exact stale_epoch refusal`,
      );
    },
  },
];

export function judgeOutbox(facts, context) {
  const assertions = OUTBOX_ASSERTIONS.map((a) => {
    let outcome;
    try {
      outcome = a.evaluate(facts, context);
    } catch (error) {
      outcome = fail(`the assertion could not be evaluated: ${error.message}`);
    }
    return {
      name: a.name,
      claim: a.claim,
      measuredBy: a.measuredBy,
      corroboratedBy: a.corroboratedBy,
      singleMeasurement: a.corroboratedBy === null,
      result: outcome.result,
      detail: outcome.detail,
    };
  });
  return {
    assertions,
    result: assertions.some((a) => a.result === "fail") ? "fail" : "pass",
  };
}
