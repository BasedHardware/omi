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
    deps.fence.store.deactivate(principal.uid);
    deps.resetWriteState();
    return json({ version: "qa-control-v1", status: "reset" });
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
    return json({ activated: result.activated, reason: result.activated ? null : result.reason });
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
