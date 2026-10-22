import { hasScope, type MemberAccess } from "@/lib/admin-access";

/**
 * Organization documents carry a `subscription` object (Stripe payment and
 * customer ids, plan, status, period) — billing data, not partner data. It
 * is readable only with finance:read, and changing it (setting or clearing
 * the payment id) requires finance:write on top of the partners scope.
 */

/** The billing block on an organization document. */
export type OrganizationSubscription = {
  subscription_id?: string;
  customer_id?: string;
  current_period_end?: number;
  cancel_at_period_end?: boolean;
  plan?: string;
  status?: string;
} | null;

type WithBilling = { subscription?: OrganizationSubscription };

/** Nulls the billing block unless the caller holds finance:read. */
export function redactBilling<T extends WithBilling>(
  organization: T,
  access: MemberAccess
): T {
  return hasScope(access, "finance:read")
    ? organization
    : { ...organization, subscription: null };
}
