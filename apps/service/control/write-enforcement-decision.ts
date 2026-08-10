import type { WriteFenceDecision } from "../../../core/control/write-fence";

/** A plan/usage refusal produced beside the account/epoch fence. */
export interface EntitlementWriteRefusal {
  readonly admitted: false;
  readonly outcome: "entitlement";
  readonly reason: "entitlement_limit_reached";
  readonly evidence: "record_nothing";
}

/** The complete decision emitted by app-facing write enforcement. */
export type WriteEnforcementDecision = WriteFenceDecision | EntitlementWriteRefusal;
