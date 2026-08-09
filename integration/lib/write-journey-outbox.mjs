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
  const op = (opId) => ({
    opId,
    domain: "tasks",
    recordId,
    payload: JSON.stringify({
      op: "create", opId, id: recordId, at: 1_000,
      description: "drained by the outbox", source: "user",
    }),
    summary: `Create task ${recordId}`,
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

  // ── the SAME journal, reopened: B1's replay ──────────────────────────────
  // A fresh Outbox over the SAME durable store is an app relaunch. If the op
  // is still pending it replays under its journaled write id and the server
  // must recognise it. This is the only place a send-time mint is visible.
  const replayStore = new MemoryStore();
  const replayEnv = new ManualEnv();
  const { box: replayBox, http: replayHttp } = await openBox({ epoch: activeEpoch, runIdForHttp: drainRunId, store: replayStore, env: replayEnv });
  await replayBox.enqueue({ ...op("outbox-op-replay"), writeId: journaled.writeId, accountEpoch: journaled.accountEpoch });
  const replayed = await drainUntil(replayEnv, async () => replayHttp.calls.some((c) => c.method === "POST"));
  const replayPost = replayHttp.calls.filter((c) => c.method === "POST").at(-1) ?? null;

  // ── the straggler: an op authored under a SUPERSEDED epoch ───────────────
  // The client's epoch provider is behind. Nothing about the op is otherwise
  // different, and nothing in the client decides it is stale — the fence does.
  const staleStore = new MemoryStore();
  const staleEnv = new ManualEnv();
  const { box: staleBox, http: staleHttp } = await openBox({ epoch: activeEpoch - 1, runIdForHttp: staleRunId, store: staleStore, env: staleEnv });
  await staleBox.enqueue(op("outbox-op-stale"));
  const stalled = await drainUntil(staleEnv, async () => (await staleBox.deadLetters()).length > 0);
  const deadLetters = await staleBox.deadLetters();

  return {
    drainRunId,
    staleRunId,
    recordId,
    journaled,
    deadAfterDrain,
    deadLetters,
    controlRefreshes,
    rounds: { drain: drained, replay: replayed, stale: stalled },
    replayResponse: replayPost === null ? null : { status: replayPost.status, text: replayPost.text },
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
