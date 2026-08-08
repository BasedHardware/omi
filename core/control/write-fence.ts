/**
 * THE ACCOUNT EPOCH FENCE — "the primary stale-client mutation fence"
 * (`backend:ADR-010` §2).
 *
 * A write carrying an epoch the account has moved past is refused here, and the
 * refusal is the point: `COORD-cross-generation-writes.md` (RATIFIED) sends a
 * straggler op deliberately *so that the fence rejects it*, because a server-side
 * rejection "is evidence we can query centrally, rather than a dead letter
 * sitting on one person's phone that we learn about only if that device reports
 * in." Until this module existed, that ruling was unimplementable and stragglers
 * had to be withheld.
 *
 * ── THE OUTCOME CLASSES, AND THE ONE THING THIS FILE MUST NOT DO ─────────────
 *
 * ADR-010 §3: "Refusals are four distinct outcomes, not one." It says why in the
 * same paragraph: ADR-004 §4 mapped 401 and 403 together onto re-authentication,
 * and "building it as written puts a user with a valid session and a missing
 * grant into a re-authentication loop that cannot succeed."
 *
 *   authentication  no valid verified identity        -> re-authenticate
 *   authorization   valid identity, no exact grant    -> surface the permission
 *   entitlement     valid grant, plan excludes it     -> route to upgrade
 *   stale epoch     control state behind the epoch    -> refresh control state
 *
 * `stale_epoch` therefore MUST NOT be conflated with `authentication`. They are
 * different instructions to the client, and collapsing them produces the exact
 * unsatisfiable loop the ADR amended ADR-004 to prevent. `write-fence.test.ts`
 * carries a red-proof for that specific mutation.
 *
 * This module decides only the class. It emits no status code and no body: the
 * wire binding belongs to the write contract, not to the fence.
 *
 * ── THE FIFTH VALUE, FLAGGED RATHER THAN SMUGGLED ────────────────────────────
 *
 * `control_unavailable` is NOT one of ADR-010 §3's four. Those four are outcomes
 * of the authorization composition — statements about the caller's authority. A
 * migration window is not: ADR-007 §4 fences writes for an account being copied,
 * and the caller's authority is perfectly fine. Missing or stale control state is
 * the same shape — this side does not know, so it does not serve.
 *
 * Conflating it with any of the four would tell a user something false during
 * every migration window. It is kept distinct and reported to the coordinator as
 * an escalation, because a fifth value on a refusal wire binds a shared wire and
 * that is above a lane's bar (`data/run-2026-08-08c/blocked/`).
 *
 * ── WHY ONE PATH PRESERVES USER CONTENT AND THE OTHERS DO NOT ────────────────
 *
 * `evidence: "preserve_envelope"` means the refused op's full envelope — patch
 * included — is retained server-side so manual resolution has something to act
 * on. `COORD-cross-generation-writes.md` is explicit that a summary is not
 * enough: "A human handed that record knows an edit was lost and roughly what it
 * was, but cannot reproduce it."
 *
 * Exactly ONE reason preserves: `request_epoch_behind`. That is the straggler,
 * and it is the only case where the op is guaranteed never to be accepted —
 * ruling B5 is built on the same fact ("Once the account epoch advances past the
 * op's epoch, the fence rejects any replay"). Every other refusal here is either
 * retryable, or resolves against the other generation, so retaining the user's
 * content would accumulate records that hold a person's data for no remedy — and
 * the retention window for exactly those rows is UNSIGNED and owed to David
 * (ruling B3). Preserving more than the ratified case would create the record
 * class before its policy exists.
 */

import type { AccountControlProjection } from "./account-control";

/** `backend:ADR-010` §3's four, plus the availability signal — see the header. */
export type WriteFenceOutcome =
  | "authentication"
  | "authorization"
  | "entitlement"
  | "stale_epoch"
  | "control_unavailable";

/** Internal. Never reaches a wire — it describes control and grant state. */
export type WriteFenceReason =
  | "control_state_absent"
  | "control_state_conflicting"
  | "control_state_not_activated"
  | "account_generation_legacy"
  | "account_generation_migrating"
  | "account_generation_rolled_back_stranded"
  | "account_lifecycle_not_active"
  | "request_epoch_absent"
  | "request_epoch_behind"
  | "request_epoch_ahead";

export type WriteFenceEvidence = "preserve_envelope" | "record_nothing";

export type WriteFenceDecision =
  | { readonly admitted: true; readonly account_epoch: number }
  | {
      readonly admitted: false;
      readonly outcome: WriteFenceOutcome;
      readonly reason: WriteFenceReason;
      readonly evidence: WriteFenceEvidence;
    };

export interface WriteFenceRequest {
  /**
   * The epoch the op was created under — the straggler stamp. `null` when the
   * request carried none at all.
   *
   * The fence is never told an account id. The projection is looked up from the
   * authenticated principal by the caller, because an identifier "conveys
   * nothing" and possession of one "is not evidence of anything"
   * (`backend:ADR-012` §4).
   */
  readonly request_epoch: number | null;
}

const refuse = (
  outcome: WriteFenceOutcome,
  reason: WriteFenceReason,
  evidence: WriteFenceEvidence,
): WriteFenceDecision => Object.freeze({ admitted: false, outcome, reason, evidence });

/**
 * The fence.
 *
 * ORDER IS LOAD-BEARING and reads top to bottom as the ADRs stack:
 *
 *   1. control state present and uncorrupted   ADR-010 §1
 *   2. lifecycle                               ADR-014 §1 — DOMINATES generation
 *   3. generation                              ADR-007 §1
 *   4. destination activation                  ADR-010 §1 step 4
 *   5. the epoch the client presented          ADR-010 §2
 *
 * Step 2 sits above step 3 because ADR-014 §1 says "Where lifecycle and
 * generation disagree, lifecycle wins", and because its alternatives table
 * rejects the generation-enum encoding precisely for making deletion "invisible
 * to paths that switch on generation". Swapping 2 and 3 admits a write to a
 * deleted account whose generation is still `new`; that mutation is this module's
 * sharpest red-proof.
 */
export const evaluateWriteFence = (
  projection: AccountControlProjection | null,
  request: WriteFenceRequest,
): WriteFenceDecision => {
  // 1. "Missing ... control state denies writes." (ADR-010 §1)
  if (projection === null) {
    return refuse("control_unavailable", "control_state_absent", "record_nothing");
  }
  // "...conflicting, or unordered..." — both land in the projection's conflict.
  if (projection.conflict !== null) {
    return refuse("control_unavailable", "control_state_conflicting", "record_nothing");
  }

  // 2. LIFECYCLE FIRST. Mapped to `authorization` rather than to a distinct
  //    "deleted" outcome on purpose: ADR-012 §4 requires that "account existence
  //    must not be probeable through response differences", and a deleted
  //    account must therefore be indistinguishable from one whose grant is
  //    missing. `deletion_pending` is included because ADR-010 §5 fences
  //    "migration, activation and background work" from the moment deletion
  //    arrives, not from the moment it completes.
  if (projection.lifecycle_state !== "active") {
    return refuse("authorization", "account_lifecycle_not_active", "record_nothing");
  }

  // 3. Generation. None of these three is a statement about the caller.
  switch (projection.account_generation) {
    case "legacy":
      // Authority has not moved. The client's op belongs to legacy and will
      // drain there; nothing is lost, so nothing is retained.
      return refuse("control_unavailable", "account_generation_legacy", "record_nothing");
    case "migrating":
      // ADR-007 §4's write fence, and the ratified migration window: "writes are
      // BLOCKED for the duration (a maintenance notice, not a local buffer)".
      // Deliberately records nothing — this is backpressure, not evidence.
      return refuse("control_unavailable", "account_generation_migrating", "record_nothing");
    case "rolled_back_stranded":
      // ADR-007 §6 restores the legacy account. The op resolves against legacy
      // once the client refreshes control state, so this is not a straggler and
      // must not accumulate user content during an incident.
      return refuse(
        "control_unavailable",
        "account_generation_rolled_back_stranded",
        "record_nothing",
      );
    case "new":
      break;
  }

  // 4. The destination must have activated EXACTLY this epoch (ADR-010 §1 step
  //    4). Generation `new` without activation is stale control state on this
  //    side, and it is also the state the rollback order deliberately creates
  //    before legacy moves.
  if (
    projection.account_epoch === null
    || projection.activation === null
    || projection.activation.activated_epoch !== projection.account_epoch
  ) {
    return refuse("control_unavailable", "control_state_not_activated", "record_nothing");
  }

  // 5. The epoch the client presented.
  const active = projection.account_epoch;
  if (request.request_epoch === null) {
    // A straggler carries the epoch it was created under; a request with none is
    // a client that never held control state. Correct instruction ("refresh
    // control state and retry"), but no envelope worth preserving — there is no
    // migration window to attribute it to.
    return refuse("stale_epoch", "request_epoch_absent", "record_nothing");
  }
  if (request.request_epoch < active) {
    // THE STRAGGLER. The account moved on while this device was offline. This op
    // will never be accepted, so this is the one refusal that preserves the
    // user's edit for manual resolution.
    return refuse("stale_epoch", "request_epoch_behind", "preserve_envelope");
  }
  if (request.request_epoch > active) {
    // THIS side is behind, not the client. Same outcome class because the
    // instruction is the same and correct — refresh control state and retry, and
    // the retry succeeds once the projection catches up. Preserving here would
    // manufacture a dead letter for an op that is about to apply.
    return refuse("stale_epoch", "request_epoch_ahead", "record_nothing");
  }

  return Object.freeze({ admitted: true, account_epoch: active });
};
