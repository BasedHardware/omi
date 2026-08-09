/**
 * THE DEV CONTROL PLANE — seeding the account-control projection, and reading
 * both producer-side arbiters, from the process that answers the write door.
 *
 * ── WHY THIS EXISTS AT ALL (R3) ──────────────────────────────────────────────
 *
 * Nothing in `platform` mints control state, by design: legacy is the authority
 * (`backend:ADR-010` §1 steps 1 and 3), no publisher exists, and an account with
 * no projection denies every write with `control_state_absent`. That fail-closed
 * posture is correct and is NOT a bug. It also means the write door cannot be
 * exercised locally at all until something seeds a projection.
 *
 * R3 rules that seeding: the local stack may drive `observe`/`activate` for its
 * **dev accounts only**, through a control-plane surface, and **the production
 * publisher remains legacy's and is untouched.** This module is that surface,
 * on the registered app rather than on a harness server — which is also what
 * lets the fence harness be retired instead of becoming a second door (R5).
 *
 * ── WHY THE COUNTERS ARE ON THIS SAME PROCESS, ON PURPOSE ────────────────────
 *
 * A counter in a sidecar is exactly the evidence shape that proved nothing in
 * wave 9: `servedCount=4 status=PASS` while the backend served zero, both
 * numbers accurate. The producer-side tallies are read from the same process
 * that produced them or they are not arbiters.
 *
 * ── THE ACCOUNT IS THE PRINCIPAL'S, EVEN HERE ────────────────────────────────
 *
 * `observe` takes an observation, and the observation carries an `account_id`.
 * This module OVERWRITES it with the authenticated principal's. A QA surface
 * that let a caller name the account whose control state it seeds would be the
 * "possession of an identifier as evidence" shape `backend:ADR-012` §4 forbids,
 * kept out of the product only by the fact that nobody deployed it. Keeping the
 * discipline here costs one line.
 */

import type { Hono } from "hono";

import type { AccountControlObservation } from "../../../core/control/account-control";
import type { WriteFenceCounter } from "../control/fence-counter";
import type { AccountControlProjectionStore } from "../control/projection-store";
import type { DevPrincipal } from "../auth/dev-token";
import type { WriteOpsCounter } from "../observability/write-ops-counter";
import type { StragglerTable } from "../stores/straggler-table";
import type { TasksReadStore } from "../stores/tasks-store";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

const UNAUTHORIZED_BODY = JSON.stringify({ error: "unauthorized" });
const BAD_REQUEST_BODY = JSON.stringify({ error: "bad_request" });

export interface QaControlRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly fence: {
    readonly store: AccountControlProjectionStore;
    readonly counter: WriteFenceCounter;
  };
  readonly writeOpsCounter: WriteOpsCounter;
  readonly stragglers: StragglerTable;
  readonly tasksRead: TasksReadStore;
  /** Ruling B5's collection, run when an epoch advance makes rows unreachable. */
  readonly collectWriteIdsBelowEpoch: (accountId: string, activeEpoch: number) => number;
  /** Drops every write-path fixture: tasks, the registry and the straggler table. */
  readonly resetWriteState: () => void;
}

const fixedResponse = (body: string, status: number): Response =>
  new Response(body, { status, headers: JSON_HEADERS });

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string") return null;
  const prefix = "Bearer ";
  if (!header.startsWith(prefix)) return null;
  const token = header.slice(prefix.length);
  return token.length > 0 ? token : null;
};

export const registerQaControlRoutes = (app: Hono, deps: QaControlRouteDependencies): void => {
  const principalOf = (context: { req: { header: (name: string) => string | undefined } }): DevPrincipal | null => {
    const token = bearerToken(context.req.header("authorization"));
    return token === null ? null : deps.resolvePrincipal(token);
  };

  const mutating = (
    path: string,
    handle: (principal: DevPrincipal, body: unknown) => Response,
  ): void => {
    app.post(path, async (context) => {
      const principal = principalOf(context);
      if (principal === null) return fixedResponse(UNAUTHORIZED_BODY, 401);
      let body: unknown;
      try {
        body = await context.req.json();
      } catch {
        return fixedResponse(BAD_REQUEST_BODY, 400);
      }
      if (body === null || typeof body !== "object" || Array.isArray(body)) {
        return fixedResponse(BAD_REQUEST_BODY, 400);
      }
      return handle(principal, body);
    });
  };

  mutating("/v1/qa/control/reset", (principal) => {
    // `forget`, not `deactivate`. Deactivating keeps the projection and its
    // control revision, so the next `observe` at revision 1 is refused as
    // `stale_observation` and the account can never be seeded from the
    // beginning again. Forgetting restores the fence's strictest state — no
    // projection, every write denies — which is where a test must start.
    const forgotten = deps.fence.store.forget(principal.uid);
    deps.resetWriteState();
    return json({ version: "qa-control-v1", status: "reset", forgotten });
  });

  mutating("/v1/qa/control/observe", (principal, body) => {
    const observation = {
      ...(body as Record<string, unknown>),
      account_id: principal.uid,
    } as AccountControlObservation;
    const result = deps.fence.store.observe(observation);
    return json({
      accepted: result.accepted,
      reason: result.accepted ? null : result.reason,
      conflicted: result.projection.conflict !== null,
    });
  });

  mutating("/v1/qa/control/activate", (principal, body) => {
    const request = body as { epoch: number; at_control_revision: number };
    const result = deps.fence.store.activate(principal.uid, request);
    // RULING B5, as a behaviour rather than a callable. An epoch advance is the
    // event that makes prior-epoch registry rows unreachable: the fence runs
    // before the registry, so every replay stamped with an older epoch is now
    // refused `stale_epoch` and its row can never be consulted again. Collecting
    // here — at the advance, not on a timer — is what grounds GC in a mechanism
    // instead of a guess about when replays stop arriving.
    const collected = result.activated ? deps.collectWriteIdsBelowEpoch(principal.uid, request.epoch) : 0;
    return json({
      activated: result.activated,
      reason: result.activated ? null : result.reason,
      write_id_rows_collected: collected,
    });
  });

  mutating("/v1/qa/control/deactivate", (principal) => {
    const projection = deps.fence.store.deactivate(principal.uid);
    return json({ deactivated: projection !== null });
  });

  /**
   * The two producer-side tallies, joined by run id.
   *
   * `null` for a run that produced nothing — never an all-zero tally, which
   * would read as "measured, and nothing happened" and is exactly the number a
   * broken join returns. Counts only: no user content, no account identifier,
   * which is why this is readable without a token for the same reason
   * `/v1/qa/status` is.
   */
  app.get("/v1/qa/control/stats", (context) => {
    const run = context.req.query("run") ?? "";
    return json({
      version: "qa-control-stats-v1",
      run,
      fence: deps.fence.counter.tally(run),
      writeOps: deps.writeOpsCounter.tally(run),
    });
  });

  /**
   * THE CONSUMER-SIDE OBSERVATION OF AN APPLY — and it is deliberately NOT a
   * read door.
   *
   * An L2 test that only reads the write door's own response is reading one
   * side of one measurement. This lets it observe, from the store, that the
   * record the door said it applied is actually there — the property the fence
   * harness could never have, because it applied nothing.
   *
   * It returns `record_id` and `revision` and **no user content**, which is the
   * line that keeps it from becoming the third door this program has already
   * paid twice for. It cannot render a task, it mints no public ids, and it
   * does not name the tasks read wire. When READ's registered route lands, this
   * endpoint's continued existence is worth re-examining — but it is not a
   * competing implementation of it, because it serves none of what that route
   * serves.
   */
  app.get("/v1/qa/control/tasks", (context) => {
    const principal = principalOf(context);
    if (principal === null) return fixedResponse(UNAUTHORIZED_BODY, 401);
    return json({
      version: "qa-control-tasks-v1",
      records: deps.tasksRead.listRecords(principal.uid)
        .map((record) => ({ record_id: record.record_id, revision: record.revision })),
    });
  });

  /**
   * The straggler export, ruling B3's export side. Token-gated, because unlike
   * the tallies this DOES return user content — the preserved envelopes are the
   * user's own refused edits, and they belong to the authenticated principal's
   * account by construction: the export takes no account parameter.
   */
  app.get("/v1/qa/control/stragglers", (context) => {
    const principal = principalOf(context);
    if (principal === null) return fixedResponse(UNAUTHORIZED_BODY, 401);
    return json({
      version: "qa-control-stragglers-v1",
      preserved: deps.stragglers.exportAccount(principal.uid),
    });
  });
};
