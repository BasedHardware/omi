/**
 * Tab-local bookkeeping for a web checkout this tab actually opened.
 *
 * Web has no return channel: `openCheckoutWindow` severs `opener`, and the
 * Stripe success page is backend-origin HTML with no script. The parent tab can
 * only observe the post-checkout focus refresh, so the record below is what
 * ties that refresh to a checkout this tab started. It never leaves the tab.
 *
 * The generated property contract (`contracts/analytics/events.json`,
 * `purchaseContract.generated.ts`) carries closed enums only and
 * `contracts/analytics/PURCHASE_EXPOSURE.md` forbids checkout/session
 * identifiers, so `checkoutId` is a dedupe key, never a transported property.
 */
export const WEB_CHECKOUT_COMPLETION_FLAG = 'web-checkout-completion';

const STORAGE_KEY = 'omi.web.checkout.pending.v1';
/** A record older than this can no longer describe a checkout this tab opened. */
const MAX_AGE_MS = 60 * 60 * 1000;

export interface PendingWebCheckout {
  checkoutId: string;
  plan: string;
  interval: string;
  source: string;
  paidBefore: boolean;
  openedAt: number;
}

function sessionStore(): Storage | null {
  try {
    if (typeof window === 'undefined') return null;
    return window.sessionStorage;
  } catch {
    // Storage can be denied outright; without it there is no verified completion.
    return null;
  }
}

function newCheckoutId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    // Fall through to the non-crypto identifier; it only ever stays in this tab.
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Stage the checkout this tab actually opened. A failed write fails closed. */
export function stageWebCheckout(
  input: Pick<PendingWebCheckout, 'plan' | 'interval' | 'source' | 'paidBefore'>,
): void {
  const store = sessionStore();
  if (!store) return;
  const record: PendingWebCheckout = {
    ...input,
    checkoutId: newCheckoutId(),
    openedAt: Date.now(),
  };
  try {
    store.setItem(STORAGE_KEY, JSON.stringify(record));
  } catch {
    // Quota denial leaves no record, so no later return can emit.
  }
}

/**
 * Consume the pending record exactly once. Removing it before the network read
 * makes two focus events, a reload or a second tab race for nothing.
 */
export function takePendingWebCheckout(now = Date.now()): PendingWebCheckout | null {
  const store = sessionStore();
  if (!store) return null;
  let raw: string | null;
  try {
    raw = store.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
  if (raw == null) return null;
  try {
    store.removeItem(STORAGE_KEY);
  } catch {
    // An unremovable record is still read once below; at-most-once also holds
    // because the only emitter consumes this same record.
  }
  try {
    const parsed = JSON.parse(raw) as Partial<PendingWebCheckout>;
    if (
      typeof parsed.checkoutId !== 'string' ||
      typeof parsed.plan !== 'string' ||
      typeof parsed.interval !== 'string' ||
      typeof parsed.source !== 'string' ||
      typeof parsed.paidBefore !== 'boolean' ||
      typeof parsed.openedAt !== 'number' ||
      now - parsed.openedAt > MAX_AGE_MS
    ) {
      return null;
    }
    return parsed as PendingWebCheckout;
  } catch {
    return null;
  }
}
