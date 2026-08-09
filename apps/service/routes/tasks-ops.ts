/**
 * THE WRITE DOOR — `POST /v1/{domain}/ops`, ruling B4, on ruling B6's first
 * writable domain.
 *
 * The write wire has been ratified and unserved: the shipped app's only POST was
 * `/v1/qa/reset`, and the account epoch fence had zero production callers. This
 * module is the endpoint that changes both, and it is the ONE module that serves
 * this path (rule 17, `WIRE_PATH_REGISTRY`).
 *
 * ── THE ORDER OF OPERATIONS, AND WHY EACH STEP IS WHERE IT IS ────────────────
 *
 *   1. AUTHENTICATE. A caller without a principal never reaches the fence, and
 *      the fence counter must not move for it — `epoch-fence.test.ts` pins that,
 *      because a fence counter that moves for a request that had no principal is
 *      a number about nothing.
 *   2. VALIDATE THE ENVELOPE with the vendored contract's own predicate. Not a
 *      re-implementation: `parseWriteOpEnvelopeJson` is the authoritative
 *      no-execution boundary for untrusted canonical JSON, and a second parser
 *      here would be two modules deciding what a valid envelope is.
 *   3. THE FENCE, per `EPOCH-fence-interface.md` — after authentication and
 *      authorization resolve, before anything is applied. The account id comes
 *      from the AUTHENTICATED PRINCIPAL, never from the body (`backend:ADR-012`
 *      §4). On `preserve_envelope`, the full envelope is retained before the
 *      refusal is written.
 *   4. THE `write_id` REGISTRY (ruling B1), and only then
 *   5. APPLY — with 4 and 5 enclosed by one storage unit of work, including
 *      recording the applied outcome before commit.
 *
 * **The fence runs BEFORE the registry, and that ordering is load-bearing.**
 * Ruling B5 grounds registry GC on exactly it: "once the account epoch advances
 * past the op's epoch, the fence rejects any replay, so prior epochs are
 * GC-able." Answering a replay from the registry ahead of the fence would make
 * that false, and GC would then drop rows a later replay could still be answered
 * from — silently converting one replay into a second apply.
 *
 * ── RESPONSE DISCIPLINE, INHERITED FROM THE READ DOOR ────────────────────────
 *
 * Every refusal body is a FIXED CONSTANT taken from the ratified contract or
 * from the fence's one HTTP binding. Nothing is interpolated — not a reason, not
 * an epoch, not an account id. The fence distinguishes five outcomes internally
 * and its `reason` field describes control and grant state; it never leaves the
 * process. `fence-contract-agreement.test.ts` is what keeps the two spellings
 * one spelling.
 *
 * ── WHAT IS NOT DECIDED HERE ─────────────────────────────────────────────────
 *
 * Task field meaning. R6: 0.5.0 is domain-generic and field bags are opaque, so
 * this route validates the envelope, applies the bag, and claims nothing about
 * what is inside it.
 */

import type { Hono } from "hono";

import {
  WRITE_ERRORS,
  WRITE_REFUSALS,
  isWritableDomain,
  parseWriteOpEnvelopeJson,
  type WriteOpEnvelope,
} from "@omi-core/ratified-contracts/write/ops";

import type { WriteFenceCounter } from "../control/fence-counter";
import { writeFenceRefusalResponse } from "../control/fence-http";
import type { AccountControlProjectionStore } from "../control/projection-store";
import { applyWriteFence } from "../control/write-fence-guard";
import type { DevPrincipal } from "../auth/dev-token";
import {
  WRITE_RUN_ID_HEADER,
  type WriteOpsCounter,
  type WriteOpsWireOutcome,
} from "../observability/write-ops-counter";
import type { StragglerTable } from "../stores/straggler-table";
import { exceedsFingerprintDepth } from "../stores/write-id-registry";
import type { WriteUnitOfWork } from "../stores/write-unit-of-work";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

/**
 * The settled path this module serves, spelled once. `WIRE_PATH_REGISTRY` names
 * this file as its only route module.
 */
export const TASKS_OPS_PATH = "/v1/tasks/ops";

/**
 * The route is mounted on the FAMILY, not on the one writable domain.
 *
 * The ratified contract builds the path from the domain (`writeOpsPath`) and
 * publishes `WRITE_OPS_PATH_PATTERN` "for a server-side router assertion", and
 * the conformance corpus pins `POST /v1/memories/ops` at **422
 * `invalid_envelope`** — a domain that is not writable is a VALIDATION failure,
 * not a missing route. Mounting only `/v1/tasks/ops` would answer that corpus
 * case 404 and tell a client the write wire does not exist rather than that its
 * envelope named a read-only domain.
 */
export const WRITE_OPS_ROUTE_PATTERN = "/v1/:domain/ops";

export interface TasksOpsRouteDependencies {
  /** Resolves a bearer token to a principal, or null. Never throws for bad input. */
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly unitOfWork: WriteUnitOfWork;
  readonly stragglers: StragglerTable;
  /** The fence's store and producer-side counter — its one composition. */
  readonly fence: {
    readonly store: AccountControlProjectionStore;
    readonly counter: WriteFenceCounter;
  };
  readonly counter: WriteOpsCounter;
  /** Injected clock, in epoch seconds. There is no wall clock in this module. */
  readonly now: () => number;
}

const fixedResponse = (body: string, status: number): Response =>
  new Response(body, { status, headers: JSON_HEADERS });

/** Extracts a bearer token without revealing which part of the header was wrong. */
const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string") return null;
  const prefix = "Bearer ";
  if (!header.startsWith(prefix)) return null;
  const token = header.slice(prefix.length);
  return token.length > 0 ? token : null;
};

/**
 * The fingerprint subject for ruling B1's replay-versus-reuse question: the
 * semantic content of the envelope, with `write_id` itself excluded because it
 * is the key, not the content.
 */
const opFingerprint = (envelope: WriteOpEnvelope): unknown => ({
  account_epoch: envelope.account_epoch,
  domain: envelope.domain,
  op: envelope.op,
});

/**
 * The one non-contract failure body. Fixed, like every other body here: an
 * exception message or a stack on this wire would describe the shape of the
 * input that produced it.
 */
const INTERNAL_BODY = JSON.stringify({ error: "internal_server_error" });

export const registerTasksOpsRoutes = (app: Hono, deps: TasksOpsRouteDependencies): void => {
  const handler = async (context: {
    req: {
      param: (name: string) => string | undefined;
      header: (name: string) => string | undefined;
      text: () => Promise<string>;
    };
  }): Promise<Response> => {
    const runId = context.req.header(WRITE_RUN_ID_HEADER);
    const answer = (outcome: WriteOpsWireOutcome, response: Response): Response => {
      // Counted from the outcome the handler REACHED, at the point the response
      // exists. Never at entry, never from an intention.
      deps.counter.record(runId, outcome);
      return response;
    };

    // ── 1. Authentication ───────────────────────────────────────────────────
    const token = bearerToken(context.req.header("authorization"));
    const principal = token === null ? null : deps.resolvePrincipal(token);
    if (principal === null) {
      const refusal = WRITE_REFUSALS.authentication;
      return answer("authentication", fixedResponse(refusal.body, refusal.status));
    }

    // ── 2. Envelope validation, by the contract's own predicate ─────────────
    let raw: string;
    try {
      raw = await context.req.text();
    } catch {
      // A body that could not be read is not an envelope. Same class, same bytes.
      return answer("validation", fixedResponse(WRITE_ERRORS.validation.body, WRITE_ERRORS.validation.status));
    }
    const envelope = parseWriteOpEnvelopeJson(raw);
    const pathDomain = context.req.param("domain");
    // The path's domain and the envelope's must agree, and both must be
    // writable. Disagreement is validation, not a route miss: a caller that
    // posts a `tasks` envelope to another domain's path has an envelope that is
    // wrong for where it sent it, and the contract's error vocabulary for "this
    // request is malformed" is exactly one value.
    if (envelope === null || !isWritableDomain(pathDomain) || envelope.domain !== pathDomain) {
      return answer("validation", fixedResponse(WRITE_ERRORS.validation.body, WRITE_ERRORS.validation.status));
    }
    // DEPTH, checked here rather than left to whichever recursion overflows
    // first. `parseWriteOpEnvelopeJson` recurses too, but at a different point
    // in the call stack, so an envelope can pass its verifier and then blow the
    // stack in the registry's fingerprint — a probe built exactly that input
    // and the route answered 500. An envelope this server will not process is
    // `validation`, the same class as any other it will not accept.
    if (exceedsFingerprintDepth(envelope.op)) {
      return answer("validation", fixedResponse(WRITE_ERRORS.validation.body, WRITE_ERRORS.validation.status));
    }

    // ── 3. The account epoch fence ──────────────────────────────────────────
    // Three lines, exactly as `EPOCH-fence-interface.md` specifies them. The
    // account id is the authenticated principal's.
    const decision = applyWriteFence(
      { store: deps.fence.store, counter: deps.fence.counter },
      { accountId: principal.uid, requestEpoch: envelope.account_epoch, runId },
    );
    if (!decision.admitted) {
      if (decision.evidence === "preserve_envelope") {
        // The user's edit is refused by a door that will never accept it, and
        // this is the only copy. Retained BEFORE the refusal is written, so a
        // failure to retain cannot be hidden by a response that already went out.
        deps.stragglers.preserve(principal.uid, {
          envelope_json: raw,
          write_id: envelope.write_id,
          account_epoch: envelope.account_epoch,
          retained_at_epoch_seconds: deps.now(),
        });
        deps.counter.recordPreservedEnvelope(runId);
      }
      return answer(decision.outcome, writeFenceRefusalResponse(decision));
    }

    // ── 4–5. The `write_id` registry and apply, as one unit of work ─────────
    const write = await deps.unitOfWork.execute({
      accountId: principal.uid,
      writeId: envelope.write_id,
      fingerprintOf: opFingerprint(envelope),
      accountEpoch: envelope.account_epoch,
      op: envelope.op,
    });
    if (write.kind === "reuse") {
      return answer(
        "write_id_reuse",
        fixedResponse(WRITE_ERRORS.write_id_reuse.body, WRITE_ERRORS.write_id_reuse.status),
      );
    }
    if (write.kind === "replay") {
      // A SUCCESS. The user's edit is in the record; reporting anything else
      // would be the false failure this contract exists to prevent.
      return answer("accepted_idempotent", fixedResponse(
        JSON.stringify({ applied: write.outcome, idempotent: true }),
        200,
      ));
    }
    if (write.kind === "conflict") {
      return answer("conflict", fixedResponse(WRITE_ERRORS.conflict.body, WRITE_ERRORS.conflict.status));
    }
    return answer("accepted", fixedResponse(
      JSON.stringify({ applied: write.outcome, idempotent: false }),
      200,
    ));
  };

  /**
   * NO CLIENT INPUT MAY PRODUCE AN UNHANDLED FAILURE. Without this, an
   * exception unwinds to the framework, which answers with whatever it likes —
   * and a probe demonstrated one: a deep-enough field bag overflowed the stack
   * inside the registry fingerprint and the route answered 500 with a trace
   * behind it. The depth bound above closes that specific input; this closes
   * the CLASS, which is the difference between fixing a bug and fixing the
   * reason it was reachable.
   *
   * Counted separately from the corpus outcomes on purpose: `internalErrors` is
   * not a `wireOutcome`, and folding it into one would make the outcome
   * vocabulary stop matching the corpus it is joined to.
   */
  const guarded = async (context: Parameters<typeof handler>[0]): Promise<Response> => {
    try {
      return await handler(context);
    } catch {
      deps.counter.recordInternalError(context.req.header(WRITE_RUN_ID_HEADER));
      return fixedResponse(INTERNAL_BODY, 500);
    }
  };

  // POST only. Every other method on this path falls through to the app's
  // `notFound`, which is the read door's discipline: an unsupported method is
  // indistinguishable from an unknown path.
  app.post(WRITE_OPS_ROUTE_PATTERN, guarded);
};
