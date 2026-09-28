/**
 * The destination's store for the account-control projection.
 *
 * ── WHAT THIS IS NOT ─────────────────────────────────────────────────────────
 *
 * It is not a storage-engine decision. This module owns the port and its
 * in-memory default. The local durable adapter lives in
 * `drivers/sqlite/service-stores/`; the production PostgreSQL adapter remains a
 * driver swap and must preserve the transition rules imported from `core/`.
 *
 * ── FAIL-CLOSED BY CONSTRUCTION ──────────────────────────────────────────────
 *
 * `read` returns `null` for an unknown account, and `evaluateWriteFence(null, …)`
 * denies. That is not a convenience: ADR-010 §1's "missing ... control state
 * denies writes" is enforced by the fence, so a store that invented a default
 * projection would silently disable the rule. There is deliberately no
 * `readOrDefault`.
 */

import {
  activateEpoch,
  admitObservation,
  deactivateEpoch,
  initialiseProjection,
  reconcileConflict,
  type AccountControlObservation,
  type AccountControlProjection,
  type ActivationResult,
  type AdmitObservationResult,
} from "../../../core/control/account-control";

export interface AccountControlProjectionStore {
  /** `null` for an account this destination has never been told about. */
  read(accountId: string): AccountControlProjection | null;
  /** Folds one legacy-published observation in. Rejections are returned, not thrown. */
  observe(observation: AccountControlObservation): AdmitObservationResult;
  /** ADR-010 §1 step 4. Refusals are returned, not thrown. */
  activate(accountId: string, request: { readonly epoch: number; readonly at_control_revision: number }): ActivationResult;
  /** ADR-010 §1 rollback step 1. No-op for an unknown account. */
  deactivate(accountId: string): AccountControlProjection | null;
  /**
   * Returns an account to "never told about". **QA reset only — not a lifecycle
   * operation**, and deliberately not reachable from any product path.
   *
   * It exists because the fence's own fail-closed posture — "missing control
   * state denies writes" — is a state a test must be able to re-enter, and
   * nothing else could produce it: `deactivate` clears the activation but keeps
   * the projection and its revision, so a fresh `observe` at revision 1 is
   * rejected as `stale_observation` and the account can never be rebuilt from
   * the beginning. The retired fence harness papered over this by discarding
   * the whole store between cases, which it could do because the store was its
   * own; the registered app's store belongs to the app.
   *
   * The direction of this operation is the reason it is safe: forgetting an
   * account makes every subsequent write DENY. It cannot be used to admit
   * anything, so it is not a hatch in the fence — it is the fence's strictest
   * state, restored.
   *
   * Returns whether an account was actually forgotten, so a caller can tell
   * "reset something" from "reset nothing".
   */
  forget(accountId: string): boolean;
  /** Clears every QA-local control projection, restoring fail-closed absence. */
  reset(): void;
  /** The only exit from a poisoned projection; requires a stated operator reason. */
  reconcile(observation: AccountControlObservation, operator: { readonly reason: string }): AdmitObservationResult;
}

export const createInMemoryAccountControlProjectionStore = (): AccountControlProjectionStore => {
  const rows = new Map<string, AccountControlProjection>();

  return Object.freeze({
    read(accountId: string): AccountControlProjection | null {
      return rows.get(accountId) ?? null;
    },

    observe(observation: AccountControlObservation): AdmitObservationResult {
      const current = rows.get(observation.account_id) ?? null;
      const result = current === null
        ? initialiseProjection(observation)
        : admitObservation(current, observation);
      // A REJECTION CAN STILL CHANGE THE ROW, and dropping the returned
      // projection would be the bug: a conflicting or unordered observation
      // poisons, and the poison is what makes every subsequent write deny. An
      // early `if (!result.accepted) return result;` here would make the fence's
      // conflict path unreachable while every unit test of the pure function
      // stayed green.
      rows.set(observation.account_id, result.projection);
      return result;
    },

    activate(
      accountId: string,
      request: { readonly epoch: number; readonly at_control_revision: number },
    ): ActivationResult {
      const current = rows.get(accountId) ?? null;
      if (current === null) return { activated: false, reason: "no_account_epoch" };
      const result = activateEpoch(current, request);
      if (result.activated) rows.set(accountId, result.projection);
      return result;
    },

    deactivate(accountId: string): AccountControlProjection | null {
      const current = rows.get(accountId) ?? null;
      if (current === null) return null;
      const next = deactivateEpoch(current);
      rows.set(accountId, next);
      return next;
    },

    forget(accountId: string): boolean {
      return rows.delete(accountId);
    },

    reset(): void {
      rows.clear();
    },

    reconcile(
      observation: AccountControlObservation,
      operator: { readonly reason: string },
    ): AdmitObservationResult {
      const current = rows.get(observation.account_id) ?? null;
      if (current === null) return initialiseProjection(observation);
      const result = reconcileConflict(current, observation, operator);
      if (result.accepted) rows.set(observation.account_id, result.projection);
      return result;
    },
  });
};
