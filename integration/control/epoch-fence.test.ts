/**
 * L2 — THE ACCOUNT EPOCH FENCE REJECTS A STALE-EPOCH WRITE, OVER REAL HTTP.
 *
 * This is the ratchet target of run 2026-08-08c, and the ratified straggler
 * ruling's hard prerequisite: `COORD-cross-generation-writes.md` sends a
 * straggler op deliberately *so that the fence rejects it*, and records that
 * "If the epoch fence is not live for a domain, that domain's stragglers are
 * withheld until it is."
 *
 * ── HOW THIS PROVES REJECTION AND NOT ABSENCE ────────────────────────────────
 *
 * The cheap version of this test — send a stale write, assert it was not a 2xx —
 * passes just as happily against a typo in the path, a crashed handler, a 404, an
 * unparsed body, or a server that refuses everything. Every one of those is
 * ABSENCE wearing a refusal's clothes, and this repo has shipped that shape
 * before.
 *
 * So every rejection assertion here is paired:
 *
 * 1. **The same envelope, differing only in `account_epoch`, is ADMITTED.** One
 *    field of one request separates 202 from 409 against the same live process,
 *    the same route and the same body grammar. A missing or broken route cannot
 *    produce the 202, so it cannot produce this pair.
 *
 * 2. **The refusal is the STALE-EPOCH class specifically**, byte-compared against
 *    the authentication refusal obtained from the same process. ADR-010 §3 exists
 *    because 401 and 403 were mapped together onto re-authentication; a fence
 *    that refused with the authentication class would satisfy "not 2xx" and be
 *    exactly the defect the ADR amended ADR-004 §4 to prevent.
 *
 * 3. **A producer-side counter and a consumer-side observation, joined by run
 *    id.** The server counts fence decisions where they are produced, keyed by
 *    the run header; the test counts the responses it received. Both are read and
 *    compared. `STATE.md`: "A dispatch-side number may never appear in a verdict."
 *    A run that produced no decision reports `null`, not zero, so a broken join
 *    fails loudly instead of agreeing with an empty expectation.
 *
 * 4. **A no-op control probe.** The counter for a run id that sent nothing is
 *    `null`. That is what distinguishes "the fence rejected 3 writes for this run"
 *    from "this counter reports 3 for everything".
 */

import { afterAll, beforeAll, beforeEach, describe, expect, test } from "bun:test";

import type { AccountControlObservation } from "../../core/control/account-control";
import { ACCOUNT_OF_PRINCIPAL, OPS_PATH, QA_BEARER, RUN_ID_HEADER } from "./fence-protocol";

const READY_TIMEOUT_MS = 20_000;
const ACTIVE_EPOCH = 7;
const STALE_EPOCH = 6;

interface LiveFenceServer {
  readonly baseUrl: string;
  stop(): Promise<void>;
}

async function freePort(): Promise<number> {
  const probe = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response("") });
  const port = probe.port ?? 0;
  await probe.stop(true);
  if (port === 0) throw new Error("could not allocate a loopback port");
  return port;
}

async function startFenceServer(): Promise<LiveFenceServer> {
  const port = await freePort();
  const child = Bun.spawn({
    cmd: ["bun", "run", "integration/control/fence-server.ts"],
    cwd: new URL("../..", import.meta.url).pathname,
    env: { ...process.env, OMI_FENCE_INTEGRATION_PORT: String(port) },
    stdout: "pipe",
    stderr: "pipe",
  });
  const baseUrl = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    // A wrapper that only polls for HTTP readiness reports success while the
    // child has already died.
    if (child.exitCode !== null) {
      const stderr = await new Response(child.stderr).text();
      throw new Error(`fence backend exited before readiness (${child.exitCode}): ${stderr}`);
    }
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) {
        return { baseUrl, async stop() { child.kill(); await child.exited; } };
      }
    } catch {
      // not up yet
    }
    await Bun.sleep(50);
  }
  child.kill();
  await child.exited;
  throw new Error(`fence backend did not become ready within ${READY_TIMEOUT_MS}ms`);
}

let server: LiveFenceServer;

const control = async (path: string, body?: unknown): Promise<Record<string, unknown>> => {
  const response = await fetch(`${server.baseUrl}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "content-type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) throw new Error(`control ${path} -> ${response.status}`);
  return (await response.json()) as Record<string, unknown>;
};

const observation = (
  overrides: Partial<AccountControlObservation> = {},
): AccountControlObservation => ({
  account_id: ACCOUNT_OF_PRINCIPAL,
  control_revision: 1,
  account_generation: "legacy",
  account_epoch: null,
  lifecycle_state: "active",
  deletion_epoch: null,
  ...overrides,
});

/** Drives ADR-010 §1's forward activation order through the live control plane. */
const cutOverLive = async (): Promise<void> => {
  await control("/control/reset", {});
  expect(await control("/control/observe", observation())).toMatchObject({ accepted: true });
  expect(await control("/control/observe", observation({
    control_revision: 2, account_generation: "migrating",
  }))).toMatchObject({ accepted: true });
  expect(await control("/control/observe", observation({
    control_revision: 3, account_generation: "new", account_epoch: ACTIVE_EPOCH,
  }))).toMatchObject({ accepted: true });
  expect(await control("/control/activate", { epoch: ACTIVE_EPOCH, at_control_revision: 3 }))
    .toMatchObject({ activated: true });
};

interface WireResponse {
  readonly status: number;
  readonly text: string;
  readonly retryAfter: string | null;
}

/** Sends a real op envelope. Returns the BYTES, never a parsed object. */
const sendOp = async (options: {
  readonly epoch?: number | null;
  readonly runId: string;
  readonly token?: string | null;
}): Promise<WireResponse> => {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    [RUN_ID_HEADER]: options.runId,
  };
  const token = options.token === undefined ? QA_BEARER : options.token;
  if (token !== null) headers["authorization"] = `Bearer ${token}`;
  const body: Record<string, unknown> = {
    op: { op: "patch", record_id: "task-fixture-1", patch: { title: "buy oat milk" } },
  };
  if (options.epoch !== undefined) body["account_epoch"] = options.epoch;
  const response = await fetch(`${server.baseUrl}${OPS_PATH}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  return {
    status: response.status,
    text: await response.text(),
    retryAfter: response.headers.get("retry-after"),
  };
};

const tallyFor = async (runId: string): Promise<Record<string, unknown> | null> => {
  const stats = await control(`/control/fence-stats?run=${encodeURIComponent(runId)}`);
  return (stats["tally"] ?? null) as Record<string, unknown> | null;
};

beforeAll(async () => {
  server = await startFenceServer();
});

afterAll(async () => {
  await server?.stop();
});

beforeEach(async () => {
  await cutOverLive();
});

describe("a stale-epoch write is REJECTED, and an identical fresh one is admitted", () => {
  /**
   * The pair. One field differs.
   *
   * red-proof: in `core/control/write-fence.ts`, delete the
   * `request.request_epoch < active` branch (so a behind epoch falls through to
   * the final `admitted: true`). The stale request then returns 202 and this goes
   * red on the first assertion — while every "not 2xx" style assertion elsewhere
   * would still pass.
   */
  test("the same envelope differing only in account_epoch gets 409 and 202", async () => {
    const run = `pair-${crypto.randomUUID()}`;
    const stale = await sendOp({ epoch: STALE_EPOCH, runId: run });
    const fresh = await sendOp({ epoch: ACTIVE_EPOCH, runId: run });

    expect(stale.status).toBe(409);
    expect(stale.text).toBe(JSON.stringify({ error: "stale_epoch", refusal_outcome: "stale_epoch" }));

    // The route exists, parses this exact body, and answers. Absence cannot.
    expect(fresh.status).toBe(202);
    expect(JSON.parse(fresh.text)).toEqual({ fence: "admitted", account_epoch: ACTIVE_EPOCH });
  });

  /**
   * ADR-010 §3: `stale_epoch` means "refresh control state and retry";
   * `authentication` means "re-authenticate". A straggler holding a valid session
   * that is told to re-authenticate enters a loop that cannot succeed — the
   * defect the ADR amended ADR-004 §4 to prevent.
   *
   * red-proof: in `write-fence.ts`, return outcome `"authentication"` for
   * `request_epoch_behind`. Both the status and the body then match the
   * unauthenticated response and this goes red.
   */
  test("the stale-epoch refusal is byte-distinct from the authentication refusal", async () => {
    const run = `classes-${crypto.randomUUID()}`;
    const stale = await sendOp({ epoch: STALE_EPOCH, runId: run });
    const unauthenticated = await sendOp({ epoch: ACTIVE_EPOCH, runId: run, token: null });

    expect(unauthenticated.status).toBe(401);
    expect(JSON.parse(unauthenticated.text).refusal_outcome).toBe("authentication");

    expect(stale.status).not.toBe(unauthenticated.status);
    expect(stale.text).not.toBe(unauthenticated.text);
    expect(JSON.parse(stale.text).refusal_outcome).toBe("stale_epoch");
  });

  test("the refusal body leaks no reason, epoch or account identifier", async () => {
    const stale = await sendOp({ epoch: STALE_EPOCH, runId: `leak-${crypto.randomUUID()}` });
    expect(Object.keys(JSON.parse(stale.text)).sort()).toEqual(["error", "refusal_outcome"]);
    for (const secret of [ACCOUNT_OF_PRINCIPAL, "request_epoch_behind", String(ACTIVE_EPOCH)]) {
      expect(stale.text).not.toContain(secret);
    }
  });
});

describe("the rejection is joinable: a producer-side counter and a consumer-side observation", () => {
  /**
   * Two independent measurements of the same three requests, joined by run id.
   *
   * red-proof: in `apps/service/control/write-fence-guard.ts`, move
   * `dependencies.counter.record(...)` above `evaluateWriteFence` and record a
   * literal `{ admitted: true, account_epoch: 0 }` — the dispatch-side number
   * STATE.md forbids. The server then reports 3 admissions for a run in which the
   * client observed one 202 and two 409s, and this goes red.
   */
  test("the server's own count of fence decisions matches what the client received", async () => {
    const run = `arbiter-${crypto.randomUUID()}`;
    const otherRun = `arbiter-other-${crypto.randomUUID()}`;

    const observed = { admitted: 0, staleEpoch: 0 };
    for (const epoch of [STALE_EPOCH, STALE_EPOCH, ACTIVE_EPOCH]) {
      const response = await sendOp({ epoch, runId: run });
      if (response.status === 202) observed.admitted += 1;
      if (response.status === 409 && JSON.parse(response.text).refusal_outcome === "stale_epoch") {
        observed.staleEpoch += 1;
      }
    }
    // Interleaved traffic under a DIFFERENT run id. A counter that only kept
    // totals would agree with the wrong answer here.
    await sendOp({ epoch: STALE_EPOCH, runId: otherRun });

    const producer = await tallyFor(run);
    expect(producer).not.toBeNull();
    expect(observed).toEqual({ admitted: 1, staleEpoch: 2 });
    expect(producer).toMatchObject({
      admitted: 1,
      refused: {
        authentication: 0, authorization: 0, entitlement: 0,
        stale_epoch: 2, control_unavailable: 0,
      },
      // The straggler is the one refusal that preserves the user's edit.
      preservedEnvelopes: 2,
    });
    expect(await tallyFor(otherRun)).toMatchObject({ refused: { stale_epoch: 1 } });
  });

  /**
   * The control probe that makes the numbers above mean something. Without it,
   * a counter hard-coded to return the same tally for every run would pass.
   */
  test("a run that sent nothing has no tally at all — null, not zero", async () => {
    expect(await tallyFor(`never-sent-${crypto.randomUUID()}`)).toBeNull();
  });

  /**
   * The fence counter must move only when the FENCE produced a decision. An
   * unauthenticated request is refused before the fence is reached.
   *
   * red-proof: in `integration/control/fence-server.ts`, move the bearer check
   * below `applyWriteFence`. The counter then records a decision for a request
   * that never had a principal, and this goes red.
   */
  test("a request refused before the fence produces no fence decision", async () => {
    const run = `pre-fence-${crypto.randomUUID()}`;
    const unauthenticated = await sendOp({ epoch: STALE_EPOCH, runId: run, token: null });
    expect(unauthenticated.status).toBe(401);
    expect(await tallyFor(run)).toBeNull();
  });
});

describe("missing, conflicting and unactivated control state deny over the wire", () => {
  /**
   * ADR-010 §1: "Missing, stale, conflicting, or unordered control state denies
   * writes." Each case below is paired with the admitted request from the same
   * process, so none of them can be satisfied by the route being broken.
   */
  test("an account the destination has never been told about is denied", async () => {
    const run = `absent-${crypto.randomUUID()}`;
    await control("/control/reset", {});
    const denied = await sendOp({ epoch: ACTIVE_EPOCH, runId: run });
    expect(denied.status).toBe(503);
    expect(JSON.parse(denied.text)).toEqual({ error: "maintenance", refusal_outcome: "control_unavailable" });
    expect(denied.retryAfter).toBe("60");

    // Pair: the identical request succeeds once control state exists.
    await cutOverLive();
    expect((await sendOp({ epoch: ACTIVE_EPOCH, runId: run })).status).toBe(202);
    expect(await tallyFor(run)).toMatchObject({ admitted: 1 });
  });

  /**
   * red-proof: in `core/control/account-control.ts`, make the same-revision
   * branch of `admitObservation` last-write-wins instead of poisoning. The
   * conflicting observation is then accepted, the fence keeps admitting, and this
   * goes red on the 503.
   */
  test("two different observations at one control revision stop writes", async () => {
    const run = `conflict-${crypto.randomUUID()}`;
    expect((await sendOp({ epoch: ACTIVE_EPOCH, runId: run })).status).toBe(202);

    const conflicting = await control("/control/observe", observation({
      control_revision: 3, account_generation: "new", account_epoch: 99,
    }));
    expect(conflicting).toMatchObject({ accepted: false, conflicted: true });

    const denied = await sendOp({ epoch: ACTIVE_EPOCH, runId: run });
    expect(denied.status).toBe(503);
    expect(JSON.parse(denied.text).refusal_outcome).toBe("control_unavailable");
  });

  /**
   * ADR-010 §1 rollback step 1 — the destination fences BEFORE legacy moves.
   *
   * red-proof: delete the activation block in `evaluateWriteFence`. The
   * deactivated account keeps serving writes and this goes red — which is the
   * window in which both generations would accept writes.
   */
  test("a deactivated epoch stops writes while legacy still says new", async () => {
    const run = `rollback-${crypto.randomUUID()}`;
    expect((await sendOp({ epoch: ACTIVE_EPOCH, runId: run })).status).toBe(202);
    expect(await control("/control/deactivate", {})).toMatchObject({ deactivated: true });
    expect((await sendOp({ epoch: ACTIVE_EPOCH, runId: run })).status).toBe(503);
  });

  /**
   * ADR-014 §1 — lifecycle dominates generation. Generation stays `new`, the
   * activation stays in place, the epoch matches exactly; only lifecycle moves.
   *
   * red-proof: move the lifecycle check below the generation switch in
   * `evaluateWriteFence`. The deleted account's write is admitted and this goes
   * red.
   *
   * ADR-012 §4 also requires that account existence not be probeable, so the
   * expected answer is 403 `authorization` — the same class a missing grant
   * produces — and NOT a distinguishable "deleted".
   */
  test("a deletion-pending account is denied as authorization, not as stale epoch", async () => {
    const run = `lifecycle-${crypto.randomUUID()}`;
    expect((await sendOp({ epoch: ACTIVE_EPOCH, runId: run })).status).toBe(202);

    expect(await control("/control/observe", observation({
      control_revision: 4,
      account_generation: "new",
      account_epoch: ACTIVE_EPOCH,
      lifecycle_state: "deletion_pending",
      deletion_epoch: 41,
    }))).toMatchObject({ accepted: true });

    const denied = await sendOp({ epoch: ACTIVE_EPOCH, runId: run });
    expect(denied.status).toBe(403);
    expect(JSON.parse(denied.text)).toEqual({ error: "forbidden", refusal_outcome: "authorization" });
  });

  /**
   * The migration window itself — ADR-007 §4's write fence, and the ratified
   * "writes are BLOCKED for the duration (a maintenance notice, not a local
   * buffer)". It must be retryable backpressure and must NOT be the stale-epoch
   * class, or the client dead-letters an op it should simply resend after the
   * window.
   */
  test("an account inside a migration window is fenced, not stale-epoched", async () => {
    const run = `window-${crypto.randomUUID()}`;
    await control("/control/reset", {});
    await control("/control/observe", observation());
    await control("/control/observe", observation({ control_revision: 2, account_generation: "migrating" }));

    const fenced = await sendOp({ epoch: ACTIVE_EPOCH, runId: run });
    expect(fenced.status).toBe(503);
    expect(JSON.parse(fenced.text).refusal_outcome).toBe("control_unavailable");
    expect(fenced.retryAfter).toBe("60");
    // No envelope is retained for backpressure: only the straggler is evidence.
    expect(await tallyFor(run)).toMatchObject({ preservedEnvelopes: 0 });
  });
});

describe("an op carrying no epoch at all", () => {
  test("is refused as stale epoch without retaining the user's content", async () => {
    const run = `noepoch-${crypto.randomUUID()}`;
    const response = await sendOp({ runId: run });
    expect(response.status).toBe(409);
    expect(JSON.parse(response.text).refusal_outcome).toBe("stale_epoch");
    expect(await tallyFor(run)).toMatchObject({
      refused: { stale_epoch: 1 }, preservedEnvelopes: 0,
    });
  });

  test("a malformed epoch is a grammar failure and never reaches the fence", async () => {
    const run = `malformed-${crypto.randomUUID()}`;
    const response = await fetch(`${server.baseUrl}${OPS_PATH}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${QA_BEARER}`,
        [RUN_ID_HEADER]: run,
      },
      body: JSON.stringify({ account_epoch: "seven", op: { op: "delete", record_id: "x" } }),
    });
    expect(response.status).toBe(400);
    expect(await tallyFor(run)).toBeNull();
  });
});
