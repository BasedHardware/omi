/** Data owned by a deployment policy, not a hidden predicate taxonomy. */
export interface CardinalityPolicy { policy_id: string; predicate_id: string; role_slot_id: string; cardinality: "single" | "many"; }
export const singleValuedKey = (policies: readonly CardinalityPolicy[], predicateId: string | undefined, roleSlotId: string): string | undefined => {
  const policy = policies.find((item) => item.predicate_id === predicateId && item.role_slot_id === roleSlotId && item.cardinality === "single");
  return policy ? `${policy.policy_id}:${policy.predicate_id}:${policy.role_slot_id}` : undefined;
};
