// domain-pending(DIV-DOMCORE-001)
/**
 * Local-process write admission for the single owner account.
 *
 * A local-first stack has exactly one account and no migration to stage.
 * Platform writes (`POST /v1/tasks/ops`, STM notes, …) fail closed until the
 * account-control projection is `new` with an activated epoch. In-process
 * tests stage that through `/v1/qa/control/observe` from revision 1; the
 * headed app does not. This helper is the process-side equivalent: call it
 * from `bin/dev-server.ts` AFTER `createLocalDevService`, and again from the
 * process-registered `afterReset` hook, never from inside the factory, so
 * those tests keep a missing projection to restage.
 *
 * Persistent QA DBs are the landmine. Restaging an already-observed row from
 * revision 1 poisons the projection and every subsequent write denies. Absent
 * → admit. Already write-ready → no-op. Any other durable state → refuse to
 * boot rather than clobber.
 */

import { evaluateAccountControlAdmission } from "../../../core/control/application-admission";
import type { AccountControlObservation } from "../../../core/control/account-control";
import type { AccountControlProjectionStore } from "../control/projection-store";

/** Same epoch the `/v1/tasks/ops` tests activate. Not a new authority. */
export const LOCAL_OWNER_ACCOUNT_EPOCH = 7;

export class LocalOwnerWriteReadyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LocalOwnerWriteReadyError";
  }
}

export type LocalOwnerWriteReadyOutcome = "admitted" | "already_ready";

const observation = (
  accountId: string,
  overrides: Partial<AccountControlObservation> = {},
): AccountControlObservation => ({
  account_id: accountId,
  control_revision: 1,
  account_generation: "legacy",
  account_epoch: null,
  lifecycle_state: "active",
  deletion_epoch: null,
  ...overrides,
});

const requireAccepted = (
  result: { readonly accepted: boolean; readonly reason?: string },
  step: string,
): void => {
  if (result.accepted) return;
  throw new LocalOwnerWriteReadyError(
    `local owner cutover failed at ${step}: ${result.reason ?? "rejected"}`,
  );
};

/**
 * Make `ownerAccountId` write-ready on this destination, or refuse.
 *
 * Returns `"admitted"` when this call walked legacy → migrating → new and
 * activated `LOCAL_OWNER_ACCOUNT_EPOCH`. Returns `"already_ready"` when the
 * projection already admits writes, regardless of epoch number.
 */
export const ensureLocalOwnerWriteReady = (
  store: AccountControlProjectionStore,
  ownerAccountId: string,
): LocalOwnerWriteReadyOutcome => {
  const current = store.read(ownerAccountId);
  const admission = evaluateAccountControlAdmission(current);
  if (admission.admitted) return "already_ready";
  if (current !== null) {
    throw new LocalOwnerWriteReadyError(
      `local owner ${ownerAccountId} has control state that is not write-ready `
      + `and will not be restaged: generation=${current.account_generation} `
      + `revision=${current.control_revision} epoch=${String(current.account_epoch)} `
      + `activated=${current.activation === null ? "none" : String(current.activation.activated_epoch)} `
      + `conflict=${current.conflict === null ? "none" : current.conflict.detail}`,
    );
  }

  requireAccepted(store.observe(observation(ownerAccountId)), "observe:legacy");
  requireAccepted(store.observe(observation(ownerAccountId, {
    control_revision: 2,
    account_generation: "migrating",
  })), "observe:migrating");
  requireAccepted(store.observe(observation(ownerAccountId, {
    control_revision: 3,
    account_generation: "new",
    account_epoch: LOCAL_OWNER_ACCOUNT_EPOCH,
  })), "observe:new");
  const activated = store.activate(ownerAccountId, {
    epoch: LOCAL_OWNER_ACCOUNT_EPOCH,
    at_control_revision: 3,
  });
  if (!activated.activated) {
    throw new LocalOwnerWriteReadyError(
      `local owner cutover failed at activate: ${activated.reason}`,
    );
  }

  const ready = evaluateAccountControlAdmission(store.read(ownerAccountId));
  if (!ready.admitted) {
    throw new LocalOwnerWriteReadyError(
      `local owner cutover finished without write admission: ${ready.reason}`,
    );
  }
  return "admitted";
};
