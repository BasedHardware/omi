import { purchasePayload, type PurchaseEventId } from './purchaseContract.generated';
import { PostHogManager } from '@/lib/analytics/posthog';

const PLANS = new Set([
  'basic',
  'plus',
  'unlimited',
  'unlimited_v2',
  'operator',
  'architect',
  'unknown',
]);

const SOURCES = new Set([
  'chat_quota_exceeded',
  'freemium_switch',
  'locked_conversation',
  'locked_memory',
  'chat_apps',
  'usage_page',
  'transcription_settings',
  'unlimited_deeplink',
  'macos_billing',
  'macos_usage_limit',
  'macos_chat_quota_banner',
  'windows_billing',
  'windows_usage_limit',
  'web_plans',
  'macos_settings_view',
  'windows_settings_view',
  'unknown',
]);

export function subscriptionPlanWire(raw: string | null | undefined): string {
  const value = raw?.trim() ?? '';
  if (value === 'free') return 'basic';
  if (value === 'pro') return 'unknown';
  return PLANS.has(value) ? value : 'unknown';
}

export function subscriptionIntervalWire(raw: string | null | undefined): string {
  const value = raw?.trim().toLowerCase() ?? '';
  // Year before month so a title that contains both words is not labeled monthly.
  if (
    value === 'year' ||
    value === 'yearly' ||
    value === 'annual' ||
    value.includes('year') ||
    value.includes('annual')
  ) {
    return 'year';
  }
  if (value === 'month' || value === 'monthly' || value.includes('month')) return 'month';
  return 'unknown';
}

export function subscriptionSourceWire(raw: string | null | undefined): string {
  const value = raw?.trim() ?? '';
  return SOURCES.has(value) ? value : 'unknown';
}

export function trackPaywallOpened(source: string, currentPlan: string): void {
  PostHogManager.track('Paywall Opened', {
    source: subscriptionSourceWire(source),
    current_plan: subscriptionPlanWire(currentPlan),
  });
}

export function trackUpgradePlanSelected(
  plan: string,
  billingInterval: string,
  source: string,
): void {
  trackPurchaseEvent('upgradeTapped', {
    plan: subscriptionPlanWire(plan),
    billing_interval: subscriptionIntervalWire(billingInterval),
    source,
  });
  PostHogManager.track('Upgrade Plan Selected', {
    plan: subscriptionPlanWire(plan),
    billing_interval: subscriptionIntervalWire(billingInterval),
    source: subscriptionSourceWire(source),
  });
}

export function trackUpgradeSucceeded(plan: string, billingInterval: string): void {
  const properties = {
    plan: subscriptionPlanWire(plan),
    billing_interval: subscriptionIntervalWire(billingInterval),
  };
  PostHogManager.track('Upgrade Succeeded Attributed', properties);
  PostHogManager.track('Upgrade Succeeded');
}

export function trackUpgradeCancelled(): void {
  PostHogManager.track('Upgrade Cancelled');
}

export function trackPurchaseEvent(
  id: PurchaseEventId,
  raw: Record<string, unknown>,
): void {
  const { name, properties } = purchasePayload(id, raw);
  try {
    PostHogManager.track(name, properties);
  } catch {
    /* Telemetry never changes purchase behavior. */
  }
}

/** Observe only a return-page navigation from this checkout window, never payment acceptance.
 * Opener isolation, a closed parent, or the bounded observation lifetime can leave it unobserved.
 * Focus/subscription refresh never completes checkout. Observer failures cannot affect purchase.
 */
export function openPurchaseCheckout(
  url: string,
  plan: string,
  interval: string,
  source: string,
) {
  const opened = window.open(url, '_blank');
  if (opened) {
    const { properties } = purchasePayload('checkoutOpened', {
      plan: subscriptionPlanWire(plan),
      billing_interval: subscriptionIntervalWire(interval),
      source,
      stage: 'hosted_checkout',
    });
    trackPurchaseEvent('checkoutOpened', { ...properties, result: 'opened' });
    try {
      const apiBase = new URL(
        process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me',
      );
      if (!['http:', 'https:'].includes(apiBase.protocol)) return opened;
      const apiOrigin = apiBase.origin;
      const dispose = () => {
        window.removeEventListener('message', onReturn);
        window.removeEventListener('pagehide', dispose);
        window.clearTimeout(timeout);
      };
      const onReturn = (event: MessageEvent) => {
        if (event.origin !== apiOrigin || event.source !== opened) return;
        if (opened.closed) {
          dispose();
          return;
        }
        if (event.data === 'omi:checkout:cancelled') {
          dispose();
        } else if (event.data === 'omi:checkout:client_navigation_completed') {
          dispose();
          trackPurchaseEvent('checkoutCompleted', {
            ...properties,
            result: 'client_navigation_completed',
          });
        }
      };
      // No persistent checkout identity or window polling. Old/abandoned flows expire.
      const timeout = window.setTimeout(dispose, 30 * 60 * 1000);
      window.addEventListener('message', onReturn);
      window.addEventListener('pagehide', dispose, { once: true });
    } catch {
      /* Optional return observation must never break existing checkout callbacks. */
    }
  }
  return opened;
}
