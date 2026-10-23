/** Copy and decisions for a subscription that is set to cancel at period end. */

export const RESUBSCRIBE_FIRST = 'Resubscribe first to change plans.';

export function yourPlanEndsOn(plan: string, date: string): string {
  return `Your ${plan} plan ends ${date}.`;
}

export function yourPlanWillRenewOn(plan: string, date: string): string {
  return `Your ${plan} plan will renew on ${date}.`;
}

export const EXISTING_SUBSCRIPTION =
  'You already have a subscription. Manage your existing subscription instead of starting a new checkout.';

function isConflict(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? '');
  return /\b409\b/.test(message);
}

/**
 * The two purchase routes use 409 for different refusals: upgrade means a
 * pending cancellation, checkout means the account already has a subscription.
 */
export function purchaseErrorMessage(
  error: unknown,
  route: 'upgrade' | 'checkout',
): string {
  if (isConflict(error))
    return route === 'upgrade' ? RESUBSCRIBE_FIRST : EXISTING_SUBSCRIPTION;
  return 'An error occurred. Please try again.';
}

/** Stripe sends unix seconds. A numeric string is accepted; anything else falls back. */
export function renewalDateSeconds(raw: unknown, fallback?: number): number | undefined {
  if (typeof raw === 'number' && raw > 0) return raw;
  if (typeof raw === 'string' && /^\d+$/.test(raw)) {
    const parsed = Number(raw);
    return parsed > 0 ? parsed : undefined;
  }
  return fallback != null && fallback > 0 ? fallback : undefined;
}
