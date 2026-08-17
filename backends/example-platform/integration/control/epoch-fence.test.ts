/**
 * L2 — THE ACCOUNT EPOCH FENCE, AND THE WRITE DOOR IT GUARDS, OVER REAL HTTP,
 * AGAINST THE SHIPPED SERVICE.
 *
 * ── WHAT CHANGED HERE, AND WHY IT HAD TO (R5) ────────────────────────────────
 *
 * This test used to spawn `integration/control/fence-server.ts`: a harness that
 * stood up its own `Bun.serve`, answered `/v1/tasks/ops` from its own handler,
 * and — its own header said so — **applied nothing**, returning
 * `202 {"fence":"admitted"}` for a write that touched no record. That was the
 * honest thing to do while no endpoint existed. It stopped being honest the
 * moment one did.
 *
 * R5 pre-ruled the consequence: when `/v1/tasks/ops` registers as a wire path,
 * the harness may not remain a second door — rebind it through the registered
 * route with only its ports faked, or retire it into the route's own L2 tests.
 * It may not take a `WIRE_PATH_HATCHES` row. **Retired** is the option taken:
 * rebinding would have left a second file constructing its own store, counter
 * and projection and calling itself the fence's harness, and the whole content
 * of rule 16 is that a second construction of one thing is a second
 * implementation.
 *
 * The divergence was not hypothetical by the time this was written. The real
 * route answers `200 {applied, idempotent}` — the status the ratified corpus
 * pins — while the untouched harness still answered `202 {"fence":"admitted"}`.
 * Anything measuring the harness was measuring bytes the product does not send.
 *
 * **Rule 17 did not catch it, and that is worth recording.** The harness named
 * the path through `OPS_PATH`, imported from a sibling constants module, so the
 * literal never appeared in the file the checker was reading and the checker
 * exited 0 with a second door standing. Verified both ways: green with the door
 * live, and firing immediately when the literal was inlined on that one line.
 * Retiring the harness also deletes that constants module, which removes the
 * bypass instance along with the door — but the bypass SHAPE is still open in
 * the checker, and that is filed for the fence's own audit, not fixed here.
 *
 * ── WHAT THIS PROCESS IS ─────────────────────────────────────────────────────
 *
 * `integration/control/live-service.ts` — `createLocalService`, the one wiring
 * the dev server and the shipped binding also use, bound to an ephemeral socket
 * and nothing else. Real: the Hono shell, the write
 * route, the epoch fence and its one HTTP binding, the tasks store, the
 * `write_id` registry, the straggler table, both producer-side counters. Faked:
 * the credential seam (dev tokens) and the SQLite memory fixture, neither of
 * which this file asserts anything about.
 *
 * A separate process, rather than an in-process call, for the reason
 * `live-server.ts` gives: the properties under test are properties of the
 * BYTES. An in-process assertion compares JavaScript objects and would pass
 * while the status code, the header set or the body framing differed — and the
 * whole content of ADR-010 §3 is that a client can tell `stale_epoch` from
 * `authentication` by what it receives.
 *
 * ── HOW THIS PROVES REJECTION AND NOT ABSENCE ────────────────────────────────
 *
 * Unchanged from the version this replaces, because the reasoning was right:
 * the cheap test — send a stale write, assert it was not a 2xx — passes just as
 * happily against a typo in the path, a crashed handler, a 404, or a server
 * that refuses everything. Every rejection assertion here is paired with the
 * same envelope differing in one field being ACCEPTED, byte-compared against a
 * different refusal class from the same process, and joined by run id to a
 * counter the server keeps where the decision is produced.
 *
 * What is new, and what the harness could not do at all: the accepted write is
 * observed IN THE STORE, through a second request, so "admitted" and "applied"
 * are two measurements rather than one word.
 */

import { afterAll, beforeAll, beforeEach, describe, expect, test } from "bun:test";

import {
  WRITE_AVAILABILITY,
  WRITE_ERRORS,
  WRITE_REFUSALS,
  isTrustedWriteAccepted,
} from "@omi-core/ratified-contracts/write/ops";

import type { AccountControlObservation } from "../../core/control/account-control";
import { WRITE_RUN_ID_HEADER } from "../../apps/service/observability/write-ops-counter";
import { TASKS_OPS_PATH } from "../../apps/service/routes/tasks-ops";

const READY_TIMEOUT_MS = 20_000;
const ACTIVE_EPOCH = 7;
const STALE_EPOCH = 6;

interface LiveService {
  readonly baseUrl: string;
  readonly devToken: string;
  readonly ownerAccountId: string;
  stop(): Promise<void>;
}

/**
 * Boots `live-service.ts` — the registered app on an ephemeral port — and reads
 * its one line of JSON.
 *
 * The dev token comes from the process this test spawned, never recomputed here
 * from the same key derivation the service uses. A test that mints its own token
 * cannot tell "the service rejected my credential" from "the service is not the
 * one I am talking to".
 */
async function startService(): Promise<LiveService> {
  const child = Bun.spawn({
    cmd: ["bun", "run", "integration/control/live-service.ts"],
    cwd: new URL("../..", import.meta.url).pathname,
    stdout: "pipe",
    stderr: "pipe",
  });
  const deadline = Date.now() + READY_TIMEOUT_MS;
  const reader = child.stdout.getReader();
  const decoder = new TextDecoder();
  let banner = "";
  let pendingRead = reader.read();

  while (Date.now() < deadline) {
    // A wrapper that only polls for HTTP readiness reports success while the
    // child has already died.
    if (child.exitCode !== null) {
      const stderr = await new Response(child.stderr).text();
      throw new Error(`live-service exited before readiness (${child.exitCode}): ${stderr}${banner}`);
    }
    // Keep one read pending. Racing a fresh reader.read() on every poll loses
    // the banner when the timeout wins but the abandoned read later consumes
    // the child's one stdout line.
    const chunk = await Promise.race([pendingRead, Bun.sleep(100).then(() => null)]);
    if (chunk !== null) {
      if (!chunk.done) banner += decoder.decode(chunk.value, { stream: true });
      pendingRead = reader.read();
    }
    const line = banner.split("\n").find((entry) => entry.includes("live_service_listening"));
    if (line === undefined) continue;
    const announced = JSON.parse(line) as { url: string; devToken: string; ownerAccountId: string };
    const response = await fetch(`${announced.url}/health`).catch(() => null);
    if (response?.ok !== true) continue;
    void reader.cancel();
    return {
      baseUrl: announced.url,
      devToken: announced.devToken,
      ownerAccountId: announced.ownerAccountId,
      async stop() { child.kill(); await child.exited; },
    };
  }
  child.kill();
  await child.exited;
  throw new Error(`live-service did not become ready within ${READY_TIMEOUT_MS}ms. Output so far:\n${banner}`);
}

let service: LiveService;
let auth: string;

beforeAll(async () => {
  service = await startService();
  auth = `Bearer ${service.devToken}`;
});

afterAll(async () => {
  await service?.stop();
});

const control = async (path: string, body?: unknown): Promise<Record<string, unknown>> => {
  const response = await fetch(`${service.baseUrl}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { authorization: auth, "content-type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) throw new Error(`control ${path} -> ${response.status}`);
  return (await response.json()) as Record<string, unknown>;
};

const observation = (
  overrides: Partial<AccountControlObservation> = {},
): Omit<AccountControlObservation, "account_id"> => {
  // `account_id` is NOT sent. The control plane takes it from the authenticated
  // principal and overwrites whatever a caller supplies — a QA surface that let
  // a caller name the account whose control state it seeds would be the
  // "possession of an identifier as evidence" shape ADR-012 §4 forbids.
  const { account_id: _ignored, ...rest } = {
    account_id: "",
    control_revision: 1,
    account_generation: "legacy",
    account_epoch: null,
    lifecycle_state: "active",
    deletion_epoch: null,
    ...overrides,
  } as AccountControlObservation;
  return rest;
};

/** Drives ADR-010 §1's forward activation order through the registered app. */
const cutOverLive = async (): Promise<void> => {
  await control("/v1/qa/control/reset", {});
  expect(await control("/v1/qa/control/observe", observation())).toMatchObject({ accepted: true });
  expect(await control("/v1/qa/control/observe", observation({
    control_revision: 2, account_generation: "migrating",
  }))).toMatchObject({ accepted: true });
  expect(await control("/v1/qa/control/observe", observation({
    control_revision: 3, account_generation: "new", account_epoch: ACTIVE_EPOCH,
  }))).toMatchObject({ accepted: true });
  expect(await control("/v1/qa/control/activate", { epoch: ACTIVE_EPOCH, at_control_revision: 3 }))
    .toMatchObject({ activated: true });
};

interface WireResponse {
  readonly status: number;
  readonly text: string;
  readonly retryAfter: string | null;
}

const writeId = (seed: string): string =>
  seed.padEnd(64, "0").slice(0, 64).replace(/[^0-9a-f]/g, "0");

/** Sends a real op envelope. Returns the BYTES, never a parsed object. */
const sendOp = async (options: {
  readonly writeId: string;
  readonly epoch?: number;
  readonly op?: unknown;
  readonly runId: string;
  readonly token?: string | null;
  readonly rawBody?: string;
}): Promise<WireResponse> => {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    [WRITE_RUN_ID_HEADER]: options.runId,
  };
  const token = options.token === undefined ? auth : options.token;
  if (token !== null) headers["authorization"] = token;
  const body = options.rawBody ?? JSON.stringify({
    write_id: options.writeId,
    account_epoch: options.epoch ?? ACTIVE_EPOCH,
    domain: "tasks",
    op: options.op ?? { op: "patch", record_id: "task-fixture-1", patch: { title: "buy oat milk" } },
  });
  const response = await fetch(`${service.baseUrl}${TASKS_OPS_PATH}`, { method: "POST", headers, body });
  return {
    status: response.status,
    text: await response.text(),
    retryAfter: response.headers.get("retry-after"),
  };
};

const statsFor = async (runId: string): Promise<Record<string, unknown>> =>
  control(`/v1/qa/control/stats?run=${encodeURIComponent(runId)}`);

const storedRecords = async (): Promise<ReadonlyArray<{ record_id: string; revision: string }>> =>
  (await control("/v1/qa/control/tasks"))["records"] as ReadonlyArray<{ record_id: string; revision: string }>;

beforeEach(async () => {
  await cutOverLive();
});

describe("a stale-epoch write is REJECTED, and an identical fresh one is APPLIED", () => {
  /**
   * The pair. One field differs.
   *
   * red-proof: in `core/control/write-fence.ts`, delete the
   * `request.request_epoch < active` branch so a behind epoch falls through to
   * the final `admitted: true`. APPLIED AND OBSERVED RED — the stale request
   * returned 200 and was applied, while every "not 2xx" style assertion
   * elsewhere would still have passed.
   */
  test("the same envelope differing only in account_epoch gets 409 and 200", async () => {
    const run = `pair-${crypto.randomUUID()}`;
    const stale = await sendOp({ writeId: writeId("a1"), epoch: STALE_EPOCH, runId: run });
    const fresh = await sendOp({ writeId: writeId("a2"), epoch: ACTIVE_EPOCH, runId: run });

    expect(stale.status).toBe(WRITE_REFUSALS.stale_epoch.status);
    expect(stale.text).toBe(WRITE_REFUSALS.stale_epoch.body);

    // The route exists, parses this exact body, and answers. Absence cannot.
    expect(fresh.status).toBe(200);
    expect(isTrustedWriteAccepted(JSON.parse(fresh.text))).toBe(true);
  });

  /**
   * THE PROPERTY THE RETIRED HARNESS COULD NOT HAVE. It answered
   * `202 {"fence":"admitted"}` and touched no record, so "the fence admits" was
   * the end of the evidence. Here the admitted write is observed a second time,
   * in the store, through a different request — and the revision the door
   * reported is the revision the store holds.
   *
   * red-proof: in `apps/service/routes/tasks-ops.ts`, return the accepted body
   * without calling `deps.tasks.apply`. APPLIED AND OBSERVED RED — the store
   * reported no records while the door reported an apply.
   */
  test("an admitted write is APPLIED, and the store agrees with the door's own answer", async () => {
    const run = `applied-${crypto.randomUUID()}`;
    const accepted = await sendOp({
      writeId: writeId("b1"), runId: run,
      op: { op: "create", record_id: "task-live-1", content: { title: "buy oat milk" } },
    });
    expect(accepted.status).toBe(200);
    const applied = JSON.parse(accepted.text).applied as { record_id: string; revision: string };

    expect(await storedRecords()).toEqual([{ record_id: applied.record_id, revision: applied.revision }]);
  });

  /**
   * ADR-010 §3: `stale_epoch` means "refresh control state"; `authentication`
   * means "re-authenticate". A straggler holding a valid session that is told
   * to re-authenticate enters a loop that cannot succeed — the defect the ADR
   * amended ADR-004 §4 to prevent.
   *
   * red-proof: in `write-fence.ts`, return outcome `"authentication"` for
   * `request_epoch_behind`. APPLIED AND OBSERVED RED — both the status and the
   * body then matched the unauthenticated response.
   */
  test("the stale-epoch refusal is byte-distinct from the authentication refusal", async () => {
    const run = `classes-${crypto.randomUUID()}`;
    const stale = await sendOp({ writeId: writeId("c1"), epoch: STALE_EPOCH, runId: run });
    const unauthenticated = await sendOp({ writeId: writeId("c2"), runId: run, token: null });

    expect(unauthenticated.status).toBe(WRITE_REFUSALS.authentication.status);
    expect(JSON.parse(unauthenticated.text).refusal_outcome).toBe("authentication");

    expect(stale.status).not.toBe(unauthenticated.status);
    expect(stale.text).not.toBe(unauthenticated.text);
    expect(JSON.parse(stale.text).refusal_outcome).toBe("stale_epoch");
  });

  test("the refusal body leaks no reason, epoch or account identifier", async () => {
    const stale = await sendOp({ writeId: writeId("d1"), epoch: STALE_EPOCH, runId: `leak-${crypto.randomUUID()}` });
    expect(Object.keys(JSON.parse(stale.text)).sort()).toEqual(["error", "refusal_outcome"]);
    for (const secret of [service.ownerAccountId, "request_epoch_behind", String(ACTIVE_EPOCH)]) {
      expect(stale.text).not.toContain(secret);
    }
  });

  /**
   * Ruling B3, on the live wire: the straggler is the one refusal that
   * preserves, and the row must be the whole envelope.
   *
   * red-proof: in `tasks-ops.ts`, make the `preserve_envelope` branch
   * unreachable. APPLIED AND OBSERVED RED — the export came back empty.
   */
  test("the refused straggler's full envelope survives, patch included", async () => {
    const run = `preserve-${crypto.randomUUID()}`;
    const stale = await sendOp({ writeId: writeId("e1"), epoch: STALE_EPOCH, runId: run });
    expect(stale.status).toBe(409);

    const exported = (await control("/v1/qa/control/stragglers"))["preserved"] as ReadonlyArray<{
      envelope_json: string; write_id: string; account_epoch: number;
    }>;
    expect(exported).toHaveLength(1);
    expect(exported[0]?.write_id).toBe(writeId("e1"));
    expect(exported[0]?.account_epoch).toBe(STALE_EPOCH);
    expect(exported[0]?.envelope_json).toContain("buy oat milk");
  });
});

describe("ruling B1's idempotency, over the wire", () => {
  /**
   * The crash-replay case: applied, crashed before the tombstone, replay. It is
   * a SUCCESS, and the store must not have moved.
   *
   * red-proof: make the `seen.kind === "replay"` branch unreachable in
   * `tasks-ops.ts`. APPLIED AND OBSERVED RED — `idempotent` came back false and
   * the stored revision advanced.
   */
  test("a replayed envelope is accepted idempotently and applies nothing", async () => {
    const run = `replay-${crypto.randomUUID()}`;
    const op = { op: "create", record_id: "task-live-2", content: { title: "first" } };
    const first = await sendOp({ writeId: writeId("f1"), runId: run, op });
    const replay = await sendOp({ writeId: writeId("f1"), runId: run, op });

    expect(JSON.parse(first.text).idempotent).toBe(false);
    expect(JSON.parse(replay.text)).toEqual({ applied: JSON.parse(first.text).applied, idempotent: true });
    expect(await storedRecords()).toEqual([JSON.parse(first.text).applied]);
  });

  /**
   * red-proof: answer `write_id_reuse` with the `conflict` bytes in
   * `tasks-ops.ts`. APPLIED AND OBSERVED RED.
   */
  test("the same write_id with different content is refused, and nothing is applied", async () => {
    const run = `reuse-${crypto.randomUUID()}`;
    await sendOp({
      writeId: writeId("f2"), runId: run,
      op: { op: "create", record_id: "task-live-3", content: { title: "first" } },
    });
    const before = await storedRecords();
    const reuse = await sendOp({
      writeId: writeId("f2"), runId: run,
      op: { op: "create", record_id: "task-live-3", content: { title: "second" } },
    });

    expect(reuse.status).toBe(WRITE_ERRORS.write_id_reuse.status);
    expect(reuse.text).toBe(WRITE_ERRORS.write_id_reuse.body);
    expect(await storedRecords()).toEqual(before);
  });

  /**
   * RULING B5, as a behaviour rather than a callable: the epoch advance is what
   * collects prior-epoch rows, because the fence refuses every replay stamped
   * with an older epoch before the registry is ever consulted.
   *
   * red-proof: change `row.accountEpoch >= activeEpoch` to `>` in
   * `write-id-registry.ts`. APPLIED AND OBSERVED RED via the unit suite; here
   * the wire-level assertion is that an advance collects the row at all.
   */
  test("advancing the epoch collects the registry rows it made unreachable", async () => {
    const run = `gc-${crypto.randomUUID()}`;
    await sendOp({ writeId: writeId("f3"), runId: run, op: { op: "create", record_id: "task-live-4", content: {} } });

    const advanced = await control("/v1/qa/control/observe", observation({
      control_revision: 4, account_generation: "new", account_epoch: ACTIVE_EPOCH + 1,
    }));
    expect(advanced).toMatchObject({ accepted: true });
    const activation = await control("/v1/qa/control/activate", {
      epoch: ACTIVE_EPOCH + 1, at_control_revision: 4,
    });
    expect(activation).toMatchObject({ activated: true, write_id_rows_collected: 1 });

    // And the replay that row would have answered is now refused by the fence,
    // which is the fact the collection is grounded on.
    const replay = await sendOp({
      writeId: writeId("f3"), epoch: ACTIVE_EPOCH, runId: run,
      op: { op: "create", record_id: "task-live-4", content: {} },
    });
    expect(replay.status).toBe(WRITE_REFUSALS.stale_epoch.status);
  });
});

describe("the door is joinable: producer-side counters and a consumer-side observation", () => {
  /**
   * Two independent measurements of the same four requests, joined by run id.
   * The server counts where the outcome is produced; this test counts what it
   * received. `STATE.md`: "A dispatch-side number may never appear in a verdict."
   *
   * red-proof: in `write-fence-guard.ts`, move `counter.record(...)` above
   * `evaluateWriteFence` and record a literal `{ admitted: true, account_epoch:
   * 0 }`. APPLIED AND OBSERVED RED — the server reported 4 admissions for a run
   * in which the client observed 2 accepted and 2 stale-epoch refusals.
   */
  test("both server-side counts match what the client received", async () => {
    const run = `arbiter-${crypto.randomUUID()}`;
    const otherRun = `arbiter-other-${crypto.randomUUID()}`;

    const observed = { accepted: 0, accepted_idempotent: 0, staleEpoch: 0 };
    const op = { op: "create", record_id: "task-live-5", content: { title: "x" } };
    for (const [seed, epoch] of [["g1", ACTIVE_EPOCH], ["g1", ACTIVE_EPOCH], ["g2", STALE_EPOCH], ["g3", STALE_EPOCH]] as const) {
      const response = await sendOp({ writeId: writeId(seed), epoch, runId: run, op });
      if (response.status === 200) {
        if (JSON.parse(response.text).idempotent === true) observed.accepted_idempotent += 1;
        else observed.accepted += 1;
      }
      if (response.status === 409 && JSON.parse(response.text).refusal_outcome === "stale_epoch") {
        observed.staleEpoch += 1;
      }
    }
    // Interleaved traffic under a DIFFERENT run id. A counter that only kept
    // totals would agree with the wrong answer here.
    await sendOp({ writeId: writeId("g4"), epoch: STALE_EPOCH, runId: otherRun });

    expect(observed).toEqual({ accepted: 1, accepted_idempotent: 1, staleEpoch: 2 });

    const stats = await statsFor(run);
    expect(stats["writeOps"]).not.toBeNull();
    expect(stats["writeOps"]).toMatchObject({
      outcomes: { accepted: 1, accepted_idempotent: 1, stale_epoch: 2, validation: 0, conflict: 0 },
      preservedEnvelopes: 2,
      // ZERO IS THE ONLY ACCEPTABLE VALUE, and it is asserted in the joined
      // test rather than left to a counter nobody reads. `internalErrors`
      // counts requests that reached the route's top-level guard — an
      // unhandled failure answered 500. A run where the client saw four
      // well-formed outcomes and the server also caught an exception is a run
      // where something was swallowed, and nothing else in this file would
      // notice: the guard returns a fixed body, so a swallowed crash on a
      // request the client never looked at is invisible from the wire.
      internalErrors: 0,
    });
    // The FENCE's independent count of the same four events: it admitted twice
    // (the replay is admitted by the fence, then answered by the registry) and
    // refused twice, preserving both stragglers.
    expect(stats["fence"]).toMatchObject({
      admitted: 2,
      refused: { authentication: 0, authorization: 0, entitlement: 0, stale_epoch: 2, control_unavailable: 0 },
      preservedEnvelopes: 2,
    });
    expect((await statsFor(otherRun))["writeOps"]).toMatchObject({ outcomes: { stale_epoch: 1 } });
  });

  /**
   * The control probe that makes the numbers above mean something. Without it,
   * a counter hard-coded to return the same tally for every run would pass.
   */
  test("a run that sent nothing has no tally at all — null, not zero", async () => {
    const stats = await statsFor(`never-sent-${crypto.randomUUID()}`);
    expect(stats["fence"]).toBeNull();
    expect(stats["writeOps"]).toBeNull();
  });

  /**
   * The fence counter must move only when the FENCE produced a decision.
   *
   * red-proof: in `tasks-ops.ts`, remove the authentication early-return and
   * let the fence run with an anonymous account id. APPLIED AND OBSERVED RED —
   * the fence recorded a decision for a request that never had a principal.
   */
  test("a request refused before the fence produces no fence decision", async () => {
    const run = `pre-fence-${crypto.randomUUID()}`;
    const unauthenticated = await sendOp({ writeId: writeId("h1"), runId: run, token: null });
    expect(unauthenticated.status).toBe(WRITE_REFUSALS.authentication.status);

    const stats = await statsFor(run);
    expect(stats["fence"]).toBeNull();
    // The ROUTE did produce an outcome. The two counters answer different
    // questions and a verdict that confused them would be measuring one thing
    // twice.
    expect(stats["writeOps"]).toMatchObject({ outcomes: { authentication: 1 } });
  });
});

describe("missing, conflicting and unactivated control state deny over the wire", () => {
  /**
   * ADR-010 §1: "Missing, stale, conflicting, or unordered control state denies
   * writes." Each case is paired with the admitted request from the same
   * process, so none can be satisfied by the route being broken.
   */
  test("an account the destination has never been told about is denied", async () => {
    const run = `absent-${crypto.randomUUID()}`;
    await control("/v1/qa/control/reset", {});
    const denied = await sendOp({ writeId: writeId("i1"), runId: run });
    expect(denied.status).toBe(WRITE_AVAILABILITY.control_unavailable.status);
    expect(denied.text).toBe(WRITE_AVAILABILITY.control_unavailable.body);
    expect(denied.retryAfter).toBe("60");

    // Pair: the identical request succeeds once control state exists.
    await cutOverLive();
    expect((await sendOp({ writeId: writeId("i1"), runId: run })).status).toBe(200);
    expect(await statsFor(run)).toMatchObject({ fence: { admitted: 1 } });
  });

  /**
   * red-proof: in `core/control/account-control.ts`, make the same-revision
   * branch of `admitObservation` last-write-wins instead of poisoning. APPLIED
   * AND OBSERVED RED — the conflicting observation was accepted and the fence
   * kept admitting.
   */
  test("two different observations at one control revision stop writes", async () => {
    const run = `conflict-${crypto.randomUUID()}`;
    expect((await sendOp({ writeId: writeId("j1"), runId: run })).status).toBe(200);

    expect(await control("/v1/qa/control/observe", observation({
      control_revision: 3, account_generation: "new", account_epoch: 99,
    }))).toMatchObject({ accepted: false, conflicted: true });

    const denied = await sendOp({ writeId: writeId("j2"), runId: run });
    expect(denied.status).toBe(WRITE_AVAILABILITY.control_unavailable.status);
    expect(JSON.parse(denied.text).refusal_outcome).toBe("control_unavailable");
  });

  /**
   * ADR-010 §1 rollback step 1 — the destination fences BEFORE legacy moves.
   *
   * red-proof: delete the activation block in `evaluateWriteFence`. APPLIED AND
   * OBSERVED RED — the deactivated account kept serving writes, which is the
   * window in which both generations would accept them.
   */
  test("a deactivated epoch stops writes while legacy still says new", async () => {
    const run = `rollback-${crypto.randomUUID()}`;
    expect((await sendOp({ writeId: writeId("k1"), runId: run })).status).toBe(200);
    expect(await control("/v1/qa/control/deactivate", {})).toMatchObject({ deactivated: true });
    expect((await sendOp({ writeId: writeId("k2"), runId: run })).status)
      .toBe(WRITE_AVAILABILITY.control_unavailable.status);
  });

  /**
   * ADR-014 §1 — lifecycle dominates generation. Generation stays `new`, the
   * activation stays in place, the epoch matches exactly; only lifecycle moves.
   * ADR-012 §4 also requires that account existence not be probeable, so the
   * expected answer is 403 `authorization` — the same class a missing grant
   * produces — and NOT a distinguishable "deleted".
   *
   * red-proof: move the lifecycle check below the generation switch in
   * `evaluateWriteFence`. APPLIED AND OBSERVED RED — the deleted account's
   * write was admitted.
   */
  test("a deletion-pending account is denied as authorization, not as stale epoch", async () => {
    const run = `lifecycle-${crypto.randomUUID()}`;
    expect((await sendOp({ writeId: writeId("l1"), runId: run })).status).toBe(200);

    expect(await control("/v1/qa/control/observe", observation({
      control_revision: 4,
      account_generation: "new",
      account_epoch: ACTIVE_EPOCH,
      lifecycle_state: "deletion_pending",
      deletion_epoch: 41,
    }))).toMatchObject({ accepted: true });

    const denied = await sendOp({ writeId: writeId("l2"), runId: run });
    expect(denied.status).toBe(WRITE_REFUSALS.authorization.status);
    expect(denied.text).toBe(WRITE_REFUSALS.authorization.body);
    // Nothing is retained: only the straggler is evidence.
    expect(await statsFor(run)).toMatchObject({ fence: { preservedEnvelopes: 0 } });
  });

  /**
   * The migration window itself — ADR-007 §4's write fence, and the ratified
   * "writes are BLOCKED for the duration (a maintenance notice, not a local
   * buffer)". It must be retryable backpressure and must NOT be the stale-epoch
   * class, or the client dead-letters an op it should simply resend.
   */
  test("an account inside a migration window is fenced, not stale-epoched", async () => {
    const run = `window-${crypto.randomUUID()}`;
    await control("/v1/qa/control/reset", {});
    await control("/v1/qa/control/observe", observation());
    await control("/v1/qa/control/observe", observation({ control_revision: 2, account_generation: "migrating" }));

    const fenced = await sendOp({ writeId: writeId("m1"), runId: run });
    expect(fenced.status).toBe(WRITE_AVAILABILITY.control_unavailable.status);
    expect(JSON.parse(fenced.text).refusal_outcome).toBe("control_unavailable");
    expect(fenced.retryAfter).toBe("60");
    // No envelope is retained for backpressure: only the straggler is evidence.
    expect(await statsFor(run)).toMatchObject({ fence: { preservedEnvelopes: 0 } });
  });
});

describe("what the ratified envelope changed about a malformed op", () => {
  /**
   * The retired harness accepted an envelope with NO `account_epoch` and mapped
   * it to the fence's `request_epoch_absent`, answering 409 `stale_epoch`. The
   * ratified envelope makes `account_epoch` REQUIRED, so the contract's own
   * predicate refuses it before the fence is reached and the answer is 422.
   *
   * That is a real behaviour change, recorded rather than quietly absorbed: the
   * harness was written before the contract ratified, and where they disagree
   * the contract wins. The property that matters is preserved either way — a
   * malformed request never counts as a fence outcome.
   */
  test("an envelope with no account_epoch is validation, and never reaches the fence", async () => {
    const run = `noepoch-${crypto.randomUUID()}`;
    const response = await sendOp({
      writeId: writeId("n1"), runId: run,
      rawBody: JSON.stringify({
        write_id: writeId("n1"), domain: "tasks",
        op: { op: "delete", record_id: "task-fixture-1" },
      }),
    });
    expect(response.status).toBe(WRITE_ERRORS.validation.status);
    expect(response.text).toBe(WRITE_ERRORS.validation.body);
    expect((await statsFor(run))["fence"]).toBeNull();
  });

  test("a malformed epoch is a grammar failure and never reaches the fence", async () => {
    const run = `malformed-${crypto.randomUUID()}`;
    const response = await sendOp({
      writeId: writeId("n2"), runId: run,
      rawBody: JSON.stringify({
        write_id: writeId("n2"), account_epoch: "seven", domain: "tasks",
        op: { op: "delete", record_id: "task-fixture-1" },
      }),
    });
    expect(response.status).toBe(WRITE_ERRORS.validation.status);
    expect((await statsFor(run))["fence"]).toBeNull();
  });
});
