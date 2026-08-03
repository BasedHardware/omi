import type { CanonicalClaim, ProvisionalClaim } from "../schema";
import { restrictivePolicyJoin } from "./policy";
import type { PolicyClass } from "./index";
import type { LiveClaimView } from "./index";

/** A deliberately small D23 grant substrate; real grant issuance/revocation remains out of scope. */
export interface Grant {
  grant_id: string;
  policy_classes: readonly PolicyClass[];
}
export interface RequestContext {
  reader_account_id: string;
  grant: Grant;
}
type PolicyBearingClaim = CanonicalClaim | ProvisionalClaim | LiveClaimView;
const samePolicy = (left: PolicyClass, right: PolicyClass): boolean =>
  left.subject_class === right.subject_class && left.sensitivity === right.sensitivity && left.capture_class === right.capture_class;

const knownValues: Readonly<Record<keyof PolicyClass, ReadonlySet<string>>> = {
  subject_class: new Set(["generic", "owner", "bystander", "restricted"]),
  sensitivity: new Set(["generic", "private", "health", "restricted"]),
  capture_class: new Set(["generic", "voice", "screen", "restricted"]),
};
const hasUnknownPolicyValue = (policy: PolicyClass): boolean =>
  !knownValues.subject_class.has(policy.subject_class) || !knownValues.sensitivity.has(policy.sensitivity) || !knownValues.capture_class.has(policy.capture_class);

/**
 * Owner identity is the single-owner whole-graph grant. Other readers require an exact,
 * explicitly issued D23 policy triple; an unknown or incomparable dimension joins to
 * restricted in the render lattice and therefore cannot accidentally match a grant.
 */
export const grantAllows = (ctx: RequestContext, claim: PolicyBearingClaim, policyClass: PolicyClass): boolean => {
  if (ctx.reader_account_id === claim.owner_account_id) return true;
  // Open-world labels have no reader-safe meaning. A reader may not turn an
  // unknown label into permission merely by repeating it in a grant.
  if (hasUnknownPolicyValue(policyClass)) return false;
  return ctx.grant.policy_classes.some((granted) => {
    if (hasUnknownPolicyValue(granted)) return false;
    const effective = restrictivePolicyJoin([granted, policyClass]);
    return samePolicy(granted, policyClass) && samePolicy(effective, policyClass);
  });
};
