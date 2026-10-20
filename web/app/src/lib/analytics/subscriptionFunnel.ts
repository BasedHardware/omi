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
