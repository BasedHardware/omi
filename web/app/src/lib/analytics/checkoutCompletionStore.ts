/**
 * Tab-local bookkeeping for a web checkout this tab actually opened.
 *
 * The checkout window is observed only through its `closed` property. Its
 * opener is severed at launch, and no return-page channel is added. The
 * session record ties a later focus refresh to the selected plan and the
 * pre-checkout subscription snapshot; checkout identifiers stay in this tab.
 */
export class WebCheckoutCompletionFlags {
  static readonly killSwitchFlag = 'web-checkout-completion';
}

export const WEB_CHECKOUT_COMPLETION_FLAG = WebCheckoutCompletionFlags.killSwitchFlag;

const STORAGE_KEY = 'omi.web.checkout.pending.v1';
/** A record older than this can no longer describe a checkout this tab opened. */
const MAX_AGE_MS = 60 * 60 * 1000;

export interface CheckoutSubscriptionSnapshot {
  plan: string | null;
  paid: boolean;
  status: string | null;
  cancelAtPeriodEnd: boolean | null;
}

export interface PendingWebCheckout {
  checkoutId: string;
  plan: string;
  interval: string;
  source: string;
  before: CheckoutSubscriptionSnapshot;
  openedAt: number;
}

const invalidatedCheckoutIds = new Set<string>();
const watchedCheckoutCounts = new Map<string, number>();

function sessionStore(): Storage | null {
  try {
    if (typeof window === 'undefined') return null;
    return window.sessionStorage;
  } catch {
    // Storage can be denied outright; without it there is no verified completion.
    return null;
  }
}

function invalidateWatchedCheckouts(): void {
  for (const checkoutId of watchedCheckoutCounts.keys()) {
    invalidatedCheckoutIds.add(checkoutId);
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

function decodePending(raw: string, now: number): PendingWebCheckout | null {
  try {
    const parsed = JSON.parse(raw) as Partial<PendingWebCheckout>;
    const before = parsed.before as Partial<CheckoutSubscriptionSnapshot> | undefined;
    if (
      typeof parsed.checkoutId !== 'string' ||
      typeof parsed.plan !== 'string' ||
      typeof parsed.interval !== 'string' ||
      typeof parsed.source !== 'string' ||
      typeof parsed.openedAt !== 'number' ||
      now < parsed.openedAt ||
      now - parsed.openedAt > MAX_AGE_MS ||
      !before ||
      !(typeof before.plan === 'string' || before.plan === null) ||
      typeof before.paid !== 'boolean' ||
      !(typeof before.status === 'string' || before.status === null) ||
      !(
        typeof before.cancelAtPeriodEnd === 'boolean' || before.cancelAtPeriodEnd === null
      )
    ) {
      return null;
    }
    return parsed as PendingWebCheckout;
  } catch {
    return null;
  }
}

/** Stage a checkout only when no other checkout is pending in this tab. */
export function stageWebCheckout(
  input: Omit<PendingWebCheckout, 'checkoutId' | 'openedAt'>,
): string | null {
  const store = sessionStore();
  if (!store) {
    invalidateWatchedCheckouts();
    return null;
  }

  let raw: string | null;
  try {
    raw = store.getItem(STORAGE_KEY);
  } catch {
    invalidateWatchedCheckouts();
    return null;
  }

  if (raw !== null) {
    const existing = decodePending(raw, Date.now());
    if (existing) invalidatedCheckoutIds.add(existing.checkoutId);
    try {
      store.removeItem(STORAGE_KEY);
    } catch {
      invalidateWatchedCheckouts();
      if (existing) invalidatedCheckoutIds.add(existing.checkoutId);
      return null;
    }
    // An unexpired record means two checkouts overlapped. Drop both signals;
    // the browser gives this tab no reliable way to attribute a return.
    if (existing) return null;
  }

  const record: PendingWebCheckout = {
    ...input,
    checkoutId: newCheckoutId(),
    openedAt: Date.now(),
  };
  try {
    store.setItem(STORAGE_KEY, JSON.stringify(record));
    return record.checkoutId;
  } catch {
    // Quota denial leaves no record, so no later return can emit.
    return null;
  }
}

/** Consume a matching pending record before awaiting any network refresh. */
export function takePendingWebCheckout(
  now = Date.now(),
  expectedCheckoutId?: string | null,
): PendingWebCheckout | null {
  const store = sessionStore();
  if (!store) {
    invalidateWatchedCheckouts();
    return null;
  }

  let raw: string | null;
  try {
    raw = store.getItem(STORAGE_KEY);
  } catch {
    invalidateWatchedCheckouts();
    return null;
  }
  if (raw == null) return null;

  const pending = decodePending(raw, now);
  if (!pending) {
    try {
      store.removeItem(STORAGE_KEY);
    } catch {
      invalidateWatchedCheckouts();
    }
    return null;
  }
  if (expectedCheckoutId && pending.checkoutId !== expectedCheckoutId) return null;
  if (invalidatedCheckoutIds.has(pending.checkoutId)) {
    try {
      store.removeItem(STORAGE_KEY);
    } catch {
      // The in-memory invalidation still prevents this page from emitting it.
    }
    return null;
  }

  try {
    store.removeItem(STORAGE_KEY);
  } catch {
    invalidatedCheckoutIds.add(pending.checkoutId);
    return null;
  }
  invalidatedCheckoutIds.delete(pending.checkoutId);
  return pending;
}

/** Drop a record when its owning component unmounts before checkout returns. */
export function discardPendingWebCheckout(checkoutId: string | null): void {
  if (!checkoutId) return;
  const store = sessionStore();
  if (!store) {
    invalidatedCheckoutIds.add(checkoutId);
    return;
  }
  try {
    const raw = store.getItem(STORAGE_KEY);
    if (raw == null) return;
    let parsed: Partial<PendingWebCheckout>;
    try {
      parsed = JSON.parse(raw) as Partial<PendingWebCheckout>;
    } catch {
      return;
    }
    if (parsed.checkoutId === checkoutId) store.removeItem(STORAGE_KEY);
  } catch {
    invalidatedCheckoutIds.add(checkoutId);
  }
}

export function registerCheckoutWatcher(checkoutId: string | null): void {
  if (!checkoutId) return;
  watchedCheckoutCounts.set(checkoutId, (watchedCheckoutCounts.get(checkoutId) ?? 0) + 1);
}

export function unregisterCheckoutWatcher(checkoutId: string | null): void {
  if (!checkoutId) return;
  const count = watchedCheckoutCounts.get(checkoutId) ?? 0;
  if (count <= 1) watchedCheckoutCounts.delete(checkoutId);
  else watchedCheckoutCounts.set(checkoutId, count - 1);
}
