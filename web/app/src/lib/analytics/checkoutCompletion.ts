import { getUserSubscription } from '@/lib/api';
import { omiFlagEnabled } from '@/lib/omiFlags';
import type { UserSubscription } from '@/types/user';

import {
  takePendingWebCheckout,
  WEB_CHECKOUT_COMPLETION_FLAG,
  type PendingWebCheckout,
} from './checkoutCompletionStore';
import {
  subscriptionIntervalWire,
  subscriptionPlanWire,
  trackPurchaseEvent,
} from './subscriptionFunnel';

/**
 * Web checkout completion is a verified paid-state transition observed on the
 * one existing post-checkout signal: the parent tab regaining focus after the
 * checkout tab closes. It is never a bare focus, page load or reload, and it
 * remains an observation rather than proof of an accepted payment.
 *
 * The generated contract only carries closed enums, and
 * `contracts/analytics/PURCHASE_EXPOSURE.md` forbids checkout/session
 * identifiers, so the tab-local `checkoutId` is a dedupe key and never a
 * transported property. day/platform/version are derived by the acceptance
 * query (`$lib=web`, event timestamp), not sent by the client.
 */
export type SubscriptionRefresh = () => void | Promise<UserSubscription | null | void>;

function isSubscription(value: unknown): value is UserSubscription {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as UserSubscription).is_unlimited === 'boolean'
  );
}

/**
 * A paid state that differs from the pre-checkout snapshot. An unknown plan,
 * an inactive subscription or a paid snapshot that did not move is not a
 * transition, so nothing is emitted.
 */
export function isVerifiedPaidTransition(
  pending: PendingWebCheckout,
  after: UserSubscription | null | undefined,
): boolean {
  if (!after || after.status === 'inactive' || !after.is_unlimited) return false;
  if (!pending.paidBefore) return true;
  return subscriptionPlanWire(after.plan) !== subscriptionPlanWire(pending.plan);
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/**
 * Re-read subscription state after the checkout tab returns focus and emit at
 * most one verified completion. The pending record is consumed before any
 * await, so a second return inside the same checkout window cannot emit again.
 * A bounded re-read absorbs webhook lag; every other outcome fails closed.
 */
export async function completeWebCheckout(
  refresh: SubscriptionRefresh,
  {
    readSubscription = getUserSubscription,
    enabled = completionEnabled,
    attempts = 3,
    retryDelayMs = 1200,
  }: {
    readSubscription?: () => Promise<UserSubscription | null>;
    enabled?: () => Promise<boolean>;
    attempts?: number;
    retryDelayMs?: number;
  } = {},
): Promise<boolean> {
  const pending = takePendingWebCheckout();
  if (!pending) {
    await refresh();
    return false;
  }

  // Refresh first so the visible plan state and the verified read describe the
  // same moment the user sees.
  let fresh: UserSubscription | undefined;
  try {
    const result = await refresh();
    fresh = isSubscription(result) ? result : undefined;
  } catch {
    // A failed UI refresh does not decide completion; the read below does.
  }

  if (!(await enabled())) return false;

  const remaining = Math.max(1, attempts);
  for (let attempt = 0; attempt < remaining; attempt += 1) {
    let after: UserSubscription | null = null;
    if (fresh !== undefined) {
      after = fresh;
      fresh = undefined;
    } else {
      try {
        after = await readSubscription();
      } catch {
        after = null;
      }
    }
    if (isVerifiedPaidTransition(pending, after)) {
      emitCompletion(pending);
      return true;
    }
    if (attempt + 1 < remaining) await sleep(retryDelayMs);
  }
  return false;
}

/**
 * Watch the one existing post-checkout signal: the parent tab regaining focus.
 * The listener is single-shot, so a bare focus, reload or later visit never
 * inspects or emits anything on its own.
 */
export function watchCheckoutReturn(refresh: SubscriptionRefresh): () => void {
  if (typeof window === 'undefined') return () => {};
  const handler = () => {
    cleanup();
    void completeWebCheckout(refresh);
  };
  const cleanup = () => {
    window.removeEventListener('focus', handler);
  };
  window.addEventListener('focus', handler);
  return cleanup;
}
