/**
 * The destination's store for the account-control projection.
 *
 * ── WHAT THIS IS NOT ─────────────────────────────────────────────────────────
 *
 * It is not the durable store. `backend:ADR-009` puts the subordinate projection
 * in PostgreSQL and `WS-003` owns that; there is no PostgreSQL adapter in this
 * repo, and SQLite here is QA fixture storage that is "never production
 * authority" (`apps/service/app-facing.ts`). Writing either one would be
 * inventing a data plane to host a record whose schema is the thing under test.
 *
 * So this is an in-memory store, said plainly rather than dressed up. What it
 * buys is real: the fence, the ordering rules and the activation protocol are
 * exercised across a real process over real HTTP against state that persists
 * between requests, which is where a fence's defects actually live. What it does
 * not buy — durability, restore behaviour, cross-node agreement — is
 * `WS-003`'s, and no test here claims it.
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
