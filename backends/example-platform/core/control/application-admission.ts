import type { AccountControlProjection } from "./account-control";

export type AccountControlAdmissionReason =
  | "control_state_absent"
  | "control_state_conflicting"
  | "control_state_not_activated"
  | "account_generation_legacy"
  | "account_generation_migrating"
  | "account_generation_rolled_back_stranded"
  | "account_lifecycle_not_active";

export type AccountControlAdmissionDecision =
  | Readonly<{ admitted: true; account_epoch: number }>
  | Readonly<{ admitted: false; reason: AccountControlAdmissionReason }>;

const deny = (reason: AccountControlAdmissionReason): AccountControlAdmissionDecision =>
  Object.freeze({ admitted: false, reason });

/**
 * Pure shared control admission for application reads, writes, and background
 * work. It authenticates no principal and emits no wire behavior.
 */
export const evaluateAccountControlAdmission = (
  projection: AccountControlProjection | null,
): AccountControlAdmissionDecision => {
  if (projection === null) return deny("control_state_absent");
  if (projection.conflict !== null) return deny("control_state_conflicting");

  // ADR-014 lifecycle dominates generation and destination activation.
  if (projection.lifecycle_state !== "active") {
    return deny("account_lifecycle_not_active");
  }

  switch (projection.account_generation) {
    case "legacy":
      return deny("account_generation_legacy");
    case "migrating":
      return deny("account_generation_migrating");
    case "rolled_back_stranded":
      return deny("account_generation_rolled_back_stranded");
    case "new":
      break;
  }

  if (projection.account_epoch === null
    || projection.activation === null
    || projection.activation.activated_epoch !== projection.account_epoch) {
    return deny("control_state_not_activated");
  }

  return Object.freeze({ admitted: true, account_epoch: projection.account_epoch });
};
