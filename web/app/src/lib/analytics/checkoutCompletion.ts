import { getUserSubscription } from '@/lib/api';
import { omiFlagEnabled } from '@/lib/omiFlags';
import type { UserSubscription } from '@/types/user';

import {
  discardPendingWebCheckout,
  registerCheckoutWatcher,
  takePendingWebCheckout,
  unregisterCheckoutWatcher,
  WEB_CHECKOUT_COMPLETION_FLAG,
  type PendingWebCheckout,
} from './checkoutCompletionStore';
import {
  subscriptionIntervalWire,
  subscriptionPlanWire,
  trackPurchaseEvent,
} from './subscriptionFunnel';

/**
 * Web has no success-page return channel. The parent waits for the checkout
 * window to close, then uses its focus/visibility refresh to verify a paid
 * transition. The checkout id remains tab-local and is never transported.
 */
export type SubscriptionRefresh = () => void | Promise<UserSubscription | null | void>;

export interface CheckoutReturnTarget {
  checkoutWindow: Window;
  checkoutId: string | null;
}

function isSubscription(value: unknown): value is UserSubscription {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as UserSubscription).plan === 'string' &&
    typeof (value as UserSubscription).status === 'string' &&
    typeof (value as UserSubscription).is_unlimited === 'boolean'
  );
}

/** A known paid state that moved from the saved subscription snapshot. */
export function isVerifiedPaidTransition(
  pending: PendingWebCheckout,
  after: UserSubscription | null | undefined,
): boolean {
  if (!after || after.status === 'inactive' || !after.is_unlimited) return false;

  const targetPlan = subscriptionPlanWire(pending.plan);
  const afterPlan = subscriptionPlanWire(after.plan);
  if (targetPlan === 'unknown' || afterPlan !== targetPlan) return false;

  const previousPlan = subscriptionPlanWire(pending.before.plan);
  const planChanged = pending.before.plan === null || previousPlan !== afterPlan;
  const becamePaid = !pending.before.paid;
  const becameActive = pending.before.status !== 'active' && after.status === 'active';
  const resumed =
    pending.before.cancelAtPeriodEnd === true && after.cancel_at_period_end === false;
  return planChanged || becamePaid || becameActive || resumed;
}

function emitCompletion(pending: PendingWebCheckout): void {
  trackPurchaseEvent('checkoutCompleted', {
    plan: subscriptionPlanWire(pending.plan),
    billing_interval: subscriptionIntervalWire(pending.interval),
    source: pending.source,
    stage: 'hosted_checkout',
    result: 'client_navigation_completed',
  });
}

async function completionEnabled(): Promise<boolean> {
  try {
    // The kill switch is on by default: only an explicit false disables it.
    return (await omiFlagEnabled(WEB_CHECKOUT_COMPLETION_FLAG)) !== false;
  } catch {
    return true;
  }
}

async function refreshSafely(refresh: SubscriptionRefresh): Promise<void> {
  try {
    await refresh();
  } catch {
    // Focus refresh failures must never turn into unhandled rejections.
  }
}

/**
 * Consume the one matching checkout before awaiting and emit only after the
 * focus refresh succeeds and reports the selected paid plan. If the refresh
 * returns no value, one authoritative read may supply it; errors and explicit
 * null results fail closed.
 */
export async function completeWebCheckout(
  refresh: SubscriptionRefresh,
  {
    readSubscription = getUserSubscription,
    enabled = completionEnabled,
    expectedCheckoutId,
  }: {
    readSubscription?: () => Promise<UserSubscription | null>;
    enabled?: () => Promise<boolean>;
    expectedCheckoutId?: string | null;
  } = {},
): Promise<boolean> {
  const pending = takePendingWebCheckout(Date.now(), expectedCheckoutId);
  if (!pending) {
    await refreshSafely(refresh);
    return false;
  }

  let result: UserSubscription | null | void;
  try {
    result = await refresh();
  } catch {
    return false;
  }
  if (result === null) return false;
  if (!(await enabled())) return false;

  let after: UserSubscription | null;
  if (isSubscription(result)) {
    after = result;
  } else {
    try {
      after = await readSubscription();
    } catch {
      return false;
    }
  }
  if (!isVerifiedPaidTransition(pending, after)) return false;

  emitCompletion(pending);
  return true;
}

/**
 * Keep the checkout observer only while its owning component is mounted. A
 * focus/visibility signal is eligible once the opened checkout window is
 * actually closed, so returning early cannot consume the pending checkout.
 */
export function watchCheckoutReturn(
  refresh: SubscriptionRefresh,
  checkout: CheckoutReturnTarget,
): () => void {
  if (typeof window === 'undefined') return () => {};

  const { checkoutWindow, checkoutId } = checkout;
  registerCheckoutWatcher(checkoutId);
  let active = true;

  const removeListeners = () => {
    if (!active) return;
    active = false;
    window.removeEventListener('focus', onReturn);
    document.removeEventListener('visibilitychange', onVisibility);
    unregisterCheckoutWatcher(checkoutId);
  };

  const cleanup = () => {
    if (!active) return;
    removeListeners();
    discardPendingWebCheckout(checkoutId);
  };

  const onReturn = () => {
    if (!active) return;
    let closed = false;
    try {
      closed = checkoutWindow.closed;
    } catch {
      cleanup();
      return;
    }
    if (!closed) return;

    removeListeners();
    if (checkoutId) {
      void completeWebCheckout(refresh, { expectedCheckoutId: checkoutId });
    } else {
      void refreshSafely(refresh);
    }
  };

  const onVisibility = () => {
    if (document.visibilityState === 'visible') onReturn();
  };

  window.addEventListener('focus', onReturn);
  document.addEventListener('visibilitychange', onVisibility);
  return cleanup;
}
