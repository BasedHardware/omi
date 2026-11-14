import { trackUpgradePlanSelected } from '@/lib/analytics/subscriptionFunnel';

/** Checkout must remain retryable when the browser refuses the new tab. */
export const CHECKOUT_POPUP_BLOCKED =
  'Your browser blocked checkout. Allow pop-ups for Omi, then try again.';

export function openCheckoutWindow(
  url: string,
  selection: { plan: string; billingInterval: string; source: string },
): boolean {
  let checkout: Window | null = null;
  try {
    // The noopener feature makes even a successful open return null, so sever
    // the opener only after retaining the handle needed for blocked detection.
    checkout = window.open(url, '_blank');
  } catch {
    // Browser policy can reject a launch with either null or an exception.
  }
  if (checkout) {
    try {
      checkout.opener = null;
    } catch {
      // An inaccessible opener does not mean the checkout tab failed to open.
    }
  }
  const opened = Boolean(checkout);
  trackUpgradePlanSelected(
    selection.plan,
    selection.billingInterval,
    selection.source,
    opened ? 'opened' : 'blocked',
  );
  return opened;
}
