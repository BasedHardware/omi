/**
 * THE ACCOUNT-CONTROL PROJECTION — the destination's subordinate copy of the
 * legacy-owned account-generation control record.
 *
 * `backend:ADR-010` §1: "While the legacy origin owns control, PostgreSQL stores
 * a subordinate destination activation/fence projection and domain migration
 * checkpoints. It may not independently transition legal account authority."
 *
 * SUBORDINATE IS THE WHOLE POINT. Nothing in this module mints a generation, an
 * epoch, or a lifecycle state. Every field arrives as an OBSERVATION published by
 * the legacy authority, and the only state this side owns is `activation` — the
 * destination's record of which epoch it has turned on (ADR-010 §1 step 4, "the
 * destination activates exactly that epoch"). A second independent authority is
 * what ADR-010 rejected outright, because "delayed or conflicting state can
 * authorize writes in both generations".
 *
 * ── WHAT THIS PROJECTION IS FOR ──────────────────────────────────────────────
 *
 * One sentence in ADR-010 §1 is the entire specification of this file:
 *
 *     "Missing, stale, conflicting, or unordered control state denies writes."
 *
 * So this module's job is not to hold a generation. It is to be able to tell,
 * mechanically, that its own copy is missing, stale, conflicting or unordered —
 * and to deny when it is. A projection that merely stored the last message it
 * received could not distinguish any of those four from healthy state, which is
 * why observations carry `control_revision` and why illegal transitions poison
 * rather than overwrite.
 *
 * ── THE TWO COORDINATES, AND WHY THEY ARE NOT ONE ────────────────────────────
 *
 * `account_generation` (ADR-007 §1) and `lifecycle_state` (ADR-014 §1) are
 * orthogonal, and lifecycle DOMINATES: "Where lifecycle and generation disagree,
 * lifecycle wins." ADR-014's alternatives table rejects folding deletion into the
 * generation enum by name, because it "makes deletion invisible to paths that
 * switch on generation". Every consumer here reads lifecycle FIRST for that
 * reason; see `write-fence.ts`, where the ordering carries a red-proof.
 *
 * ── THE ACCOUNT IDENTIFIER, AND WHAT IS DELIBERATELY NOT IMPLEMENTED ─────────
 *
 * `account_id` is the platform-owned account identifier of `backend:ADR-012` §1,
 * which is SETTLED. §2's identifier *grammar* is NOT: it is blocked on
 * reconciliation with `frontend:ADR-006` (RISK-015), and until that reconciles
 * "neither scheme is implemented in a shared contract."
 *
 * Therefore this module treats `account_id` as an OPAQUE token and validates only
 * that it is a bounded, non-empty, whitespace-free string. It does not mint one,
 * does not parse a type prefix, and does not know what a word is. Writing
 * `^acct_(\w+-){3}\w+$` here would be implementing §2's grammar in the one place
 * a future wire would inherit it from — exactly what RISK-015 forbids.
 *
 * It also never crosses a wire. The fence is driven by the authenticated
 * principal, never by a caller-supplied account id; see `write-fence.ts`.
 */

/** `backend:ADR-007` §1. The only legal account generations. */
export type AccountGeneration = "legacy" | "migrating" | "new" | "rolled_back_stranded";

/** `backend:ADR-014` §1. Orthogonal to generation, and dominant over it. */
export type AccountLifecycleState = "active" | "deletion_pending" | "deleted";

/**
 * One publication from the legacy control authority.
 *
 * `control_revision` is what makes ordering decidable. Without it a late
 * redelivery and a fresh transition are indistinguishable, and "unordered control
 * state denies writes" is unenforceable — the projection would simply overwrite
 * itself with whichever message arrived last and report perfect health.
 */
export interface AccountControlObservation {
  readonly account_id: string;
  /** Monotonic, minted by the legacy authority. Orders observations. */
  readonly control_revision: number;
  readonly account_generation: AccountGeneration;
  /**
   * Assigned by the legacy CAS to `new` (ADR-010 §1 step 3) and monotonic
   * thereafter. `null` before an account has ever been cut over.
   */
  readonly account_epoch: number | null;
  readonly lifecycle_state: AccountLifecycleState;
  /** `backend:ADR-014` §1: "A deletion epoch accompanies the state." */
  readonly deletion_epoch: number | null;
}

/**
 * The destination's own activation record — the ONLY field on this side that the
 * platform writes for itself, and it is still not authority: it can activate
 * exactly the epoch the control record already carries, and nothing else.
 */
export interface DestinationActivation {
  readonly activated_epoch: number;
  /** The control revision the activation was taken against. */
  readonly at_control_revision: number;
}

/**
 * A conflict is TERMINAL until an operator reconciles it. ADR-010's consequence
 * is explicit: "The new backend sacrifices write availability rather than
 * guessing when control state is missing or stale."
 */
export interface AccountControlConflict {
  readonly at_control_revision: number;
  readonly detail: AccountControlRejection;
}

export interface AccountControlProjection {
  readonly account_id: string;
  readonly control_revision: number;
  readonly account_generation: AccountGeneration;
  readonly account_epoch: number | null;
  readonly lifecycle_state: AccountLifecycleState;
  readonly deletion_epoch: number | null;
  readonly activation: DestinationActivation | null;
  /** Non-null poisons the projection: every write denies until reconciled. */
  readonly conflict: AccountControlConflict | null;
}

/** Why an observation was not accepted. Internal; never reaches a wire. */
export type AccountControlRejection =
  | "malformed_observation"
  | "account_id_mismatch"
  | "stale_observation"
  | "conflicting_observation"
  | "unordered_generation_transition"
  | "unordered_epoch"
  | "withdrawn_epoch"
  | "unordered_lifecycle"
  | "mutated_deletion_epoch"
  | "projection_conflicted";

export type AdmitObservationResult =
  | { readonly accepted: true; readonly projection: AccountControlProjection }
  | {
      readonly accepted: false;
      readonly reason: AccountControlRejection;
      /** The projection as it now stands — poisoned, if the rejection poisons. */
      readonly projection: AccountControlProjection;
    };

const MAX_ACCOUNT_ID_LENGTH = 128;

/**
 * ADR-012 §2's grammar is blocked (RISK-015), so this is a containment check and
 * not an identifier grammar: bounded, non-empty, no whitespace, no control
 * characters. It accepts a Firebase-shaped id and a word slug alike, on purpose.
 */
export const isWellFormedAccountId = (value: unknown): value is string =>
  typeof value === "string"
  && value.length > 0
  && value.length <= MAX_ACCOUNT_ID_LENGTH
  && /^[\x21-\x7e]+$/.test(value);

const isEpoch = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const isNullableEpoch = (value: unknown): value is number | null => value === null || isEpoch(value);

const GENERATIONS: ReadonlySet<string> = new Set<AccountGeneration>([
  "legacy",
  "migrating",
  "new",
  "rolled_back_stranded",
]);

const LIFECYCLE_ORDER: Readonly<Record<AccountLifecycleState, number>> = Object.freeze({
  active: 0,
  deletion_pending: 1,
  deleted: 2,
});

/**
 * Legal generation transitions, straight out of `backend:ADR-007`:
 *
 *   §1  legacy -> migrating -> new
 *                          \-> rolled_back_stranded
 *   §4  "A failed migration remains fenced/resumable or returns to `legacy`"
 *   §6  rollback from `new` preserves post-cutover data as stranded
 *
 * `rolled_back_stranded` is TERMINAL here. Re-cutover is explicitly undecided —
 * ADR-014 §8 lists "whether re-cutover is permitted" among the policies gated at
 * the first production cohort — and inventing a transition out of it would be
 * this module deciding a policy question by omission.
 */
const LEGAL_GENERATION_TRANSITIONS: Readonly<Record<AccountGeneration, readonly AccountGeneration[]>> =
  Object.freeze({
    legacy: ["legacy", "migrating"],
    migrating: ["migrating", "new", "legacy", "rolled_back_stranded"],
    new: ["new", "rolled_back_stranded"],
    rolled_back_stranded: ["rolled_back_stranded"],
  });

const isWellFormedObservation = (value: AccountControlObservation): boolean =>
  isWellFormedAccountId(value.account_id)
  && isEpoch(value.control_revision)
  && GENERATIONS.has(value.account_generation)
  && isNullableEpoch(value.account_epoch)
  && Object.prototype.hasOwnProperty.call(LIFECYCLE_ORDER, value.lifecycle_state)
  && isNullableEpoch(value.deletion_epoch)
  // ADR-014 §1: "A deletion epoch accompanies the state." A terminal lifecycle
  // with no deletion epoch is an incomplete record, not a usable one.
  && (value.lifecycle_state === "active" || value.deletion_epoch !== null)
  && (value.lifecycle_state !== "active" || value.deletion_epoch === null);

const sameObservation = (
  left: AccountControlProjection,
  right: AccountControlObservation,
): boolean =>
  left.account_id === right.account_id
  && left.control_revision === right.control_revision
  && left.account_generation === right.account_generation
  && left.account_epoch === right.account_epoch
  && left.lifecycle_state === right.lifecycle_state
  && left.deletion_epoch === right.deletion_epoch;

const project = (
  observation: AccountControlObservation,
  activation: DestinationActivation | null,
  conflict: AccountControlConflict | null,
): AccountControlProjection =>
  Object.freeze({
    account_id: observation.account_id,
    control_revision: observation.control_revision,
    account_generation: observation.account_generation,
    account_epoch: observation.account_epoch,
    lifecycle_state: observation.lifecycle_state,
    deletion_epoch: observation.deletion_epoch,
    activation,
    conflict,
  });

const poison = (
  current: AccountControlProjection,
  reason: AccountControlRejection,
  atControlRevision: number,
): AdmitObservationResult => ({
  accepted: false,
  reason,
  projection: Object.freeze({
    ...current,
    conflict: current.conflict ?? Object.freeze({ at_control_revision: atControlRevision, detail: reason }),
  }),
});

/**
 * Accepts the FIRST observation for an account. Deliberately separate from
 * `admitObservation`: bootstrapping and transitioning are different questions,
 * and a single function that silently accepts anything when `current` is null is
 * how "missing control state" quietly becomes "whatever arrived first".
 */
export const initialiseProjection = (
  observation: AccountControlObservation,
): AdmitObservationResult => {
  if (!isWellFormedObservation(observation)) {
    return {
      accepted: false,
      reason: "malformed_observation",
      // There is nothing to poison: no projection exists, and "missing control
      // state denies writes" already covers this account.
      projection: project(observation, null, Object.freeze({
        at_control_revision: -1,
        detail: "malformed_observation",
      })),
    };
  }
  return { accepted: true, projection: project(observation, null, null) };
};

/**
 * Folds one observation into the projection.
 *
 * The four denial-worthy states of ADR-010 §1 map onto this function as follows:
 *
 * - MISSING     — no projection at all; the caller's `read` returns null and the
 *                 fence denies. Not this function's case.
 * - STALE       — `stale_observation`: an observation at or below the accepted
 *                 revision. Dropped, NOT poisoning: redelivery is ordinary.
 * - CONFLICTING — two different contents at the SAME revision. Poisons.
 * - UNORDERED   — a higher revision carrying a transition that cannot legally
 *                 follow the accepted one. Poisons.
 *
 * Stale is the only one that does not poison, and the asymmetry is deliberate: a
 * duplicate delivery is a normal property of any publisher, whereas two different
 * truths at one revision, or an illegal transition, mean this side cannot know
 * the account's state — and guessing is what ADR-010 forbids.
 */
export const admitObservation = (
  current: AccountControlProjection,
  observation: AccountControlObservation,
): AdmitObservationResult => {
  if (current.conflict !== null) {
    // A poisoned projection does not heal by receiving more messages from the
    // publisher that poisoned it. Reconciliation is an explicit operator act.
    return { accepted: false, reason: "projection_conflicted", projection: current };
  }
  if (!isWellFormedObservation(observation)) {
    return poison(current, "malformed_observation", observation.control_revision);
  }
  if (observation.account_id !== current.account_id) {
    // Two account identifiers at one projection key is split brain over the most
    // safety-critical key in the system (ADR-014 §2).
    return poison(current, "account_id_mismatch", observation.control_revision);
  }
  if (observation.control_revision < current.control_revision) {
    return { accepted: false, reason: "stale_observation", projection: current };
  }
  if (observation.control_revision === current.control_revision) {
    if (sameObservation(current, observation)) {
      return { accepted: true, projection: current };
    }
    return poison(current, "conflicting_observation", observation.control_revision);
  }

  if (!LEGAL_GENERATION_TRANSITIONS[current.account_generation].includes(observation.account_generation)) {
    return poison(current, "unordered_generation_transition", observation.control_revision);
  }
  if (current.account_epoch !== null) {
    if (observation.account_epoch === null) {
      // ADR-010 §1 step 3 makes the epoch monotonic. An epoch that disappears
      // would let a stale client's op match `null` and be admitted.
      return poison(current, "withdrawn_epoch", observation.control_revision);
    }
    if (observation.account_epoch < current.account_epoch) {
      return poison(current, "unordered_epoch", observation.control_revision);
    }
  }
  if (LIFECYCLE_ORDER[observation.lifecycle_state] < LIFECYCLE_ORDER[current.lifecycle_state]) {
    // `active -> deletion_pending -> deleted` is one-way (ADR-014 §1). A
    // resurrection arriving as an ordinary observation is exactly the restore
    // hazard ADR-014 §4 exists for, and it must not be applied silently.
    return poison(current, "unordered_lifecycle", observation.control_revision);
  }
  if (current.deletion_epoch !== null && observation.deletion_epoch !== current.deletion_epoch) {
    return poison(current, "mutated_deletion_epoch", observation.control_revision);
  }

  // An accepted observation that moves the account off the activated epoch
  // invalidates the activation: ADR-010 §1 step 4 activates EXACTLY one epoch,
  // and the destination must re-activate rather than inherit.
  const activation = current.activation !== null
    && observation.account_epoch === current.activation.activated_epoch
    && observation.account_generation === "new"
    ? current.activation
    : null;
  return { accepted: true, projection: project(observation, activation, null) };
};

export type ActivationRefusal =
  | "projection_conflicted"
  | "account_generation_not_new"
  | "account_lifecycle_not_active"
  | "no_account_epoch"
  | "epoch_mismatch"
  | "control_revision_mismatch"
  | "activation_not_monotonic";

export type ActivationResult =
  | { readonly activated: true; readonly projection: AccountControlProjection }
  | { readonly activated: false; readonly reason: ActivationRefusal };

/**
 * Step 4 of ADR-010 §1's forward activation order: "The destination activates
 * exactly that epoch."
 *
 * EXACTLY is the operative word and it is why this takes an epoch argument at all
 * rather than reading one off the projection. An activation call that simply
 * adopted whatever epoch the projection held could not fail, and a step that
 * cannot fail is not a step in a protocol — it is a comment. Passing the epoch
 * the operator believes is being activated, and refusing when it is not the
 * epoch the control record carries, is what makes the order checkable.
 */
export const activateEpoch = (
  projection: AccountControlProjection,
  request: { readonly epoch: number; readonly at_control_revision: number },
): ActivationResult => {
  if (projection.conflict !== null) return { activated: false, reason: "projection_conflicted" };
  if (projection.account_generation !== "new") return { activated: false, reason: "account_generation_not_new" };
  // Lifecycle dominates generation (ADR-014 §1) — including here, where the
  // destination would otherwise turn writes on for an account being deleted.
  if (projection.lifecycle_state !== "active") return { activated: false, reason: "account_lifecycle_not_active" };
  if (projection.account_epoch === null) return { activated: false, reason: "no_account_epoch" };
  if (!isEpoch(request.epoch) || request.epoch !== projection.account_epoch) {
    return { activated: false, reason: "epoch_mismatch" };
  }
  if (request.at_control_revision !== projection.control_revision) {
    // Activating against a revision the projection has already moved past is
    // activating a snapshot of the past. Stale control state denies.
    return { activated: false, reason: "control_revision_mismatch" };
  }
  if (projection.activation !== null && request.epoch < projection.activation.activated_epoch) {
    return { activated: false, reason: "activation_not_monotonic" };
  }
  return {
    activated: true,
    projection: Object.freeze({
      ...projection,
      activation: Object.freeze({
        activated_epoch: request.epoch,
        at_control_revision: request.at_control_revision,
      }),
    }),
  };
};

/**
 * Step 1 of ADR-010 §1's ROLLBACK order: "The destination fences/deactivates the
 * epoch and drains or rejects work."
 *
 * Deactivation happens BEFORE legacy compare-and-swaps to `rolled_back_stranded`,
 * which is why it cannot be expressed as a generation observation. Without it the
 * rollback order is unimplementable in the stated sequence: the destination would
 * have to wait for legacy to move first, and the window in between is precisely
 * the one where both generations can accept writes.
 */
export const deactivateEpoch = (
  projection: AccountControlProjection,
): AccountControlProjection => Object.freeze({ ...projection, activation: null });

/**
 * The one way out of a poisoned projection, and it requires a stated reason.
 *
 * ADR-010 §4: "Any operator action is separately authenticated, scoped, expiring,
 * reasoned and audited." Authentication, scope and expiry belong to whatever
 * operator surface eventually calls this — none exists yet, and this module is
 * not the place to invent one. What this signature CAN enforce is that a reason
 * exists and that reconciliation is never an accident of ordinary message flow.
 */
export const reconcileConflict = (
  projection: AccountControlProjection,
  observation: AccountControlObservation,
  operator: { readonly reason: string },
): AdmitObservationResult => {
  if (operator.reason.trim().length === 0) {
    return { accepted: false, reason: "projection_conflicted", projection };
  }
  if (!isWellFormedObservation(observation)) {
    return { accepted: false, reason: "malformed_observation", projection };
  }
  if (observation.account_id !== projection.account_id) {
    return { accepted: false, reason: "account_id_mismatch", projection };
  }
  // Reconciliation restates the account's control state from the authority and
  // clears the activation: whatever the destination had turned on was decided
  // against state now known to be untrustworthy.
  return { accepted: true, projection: project(observation, null, null) };
};
