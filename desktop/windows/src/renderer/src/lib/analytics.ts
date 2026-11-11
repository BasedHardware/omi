import { purchasePayload, type PurchaseEventId } from './purchaseContract.generated'
// Mirrors the macOS desktop app's PostHogManager: best-effort analytics sent to
// the same PostHog project via its HTTP ingestion API (no SDK needed). The project
// key is a publishable client key — safe to embed, exactly as the desktop app
// hardcodes it. Every call is fire-and-forget and never blocks or surfaces errors.
import { auth } from './firebase'

// Host is intentionally fixed to the CSP connect-src allowlist in renderer HTML.
// A VITE_POSTHOG_HOST override would silently fail under Chromium if it diverged.
const POSTHOG_HOST = 'https://us.i.posthog.com'
const POSTHOG_KEY =
  (import.meta.env.VITE_POSTHOG_KEY as string) || 'phc_z3qUFhGUgYIOMYnfxVSrLmYISQvbgph8iREQv3sez3Y'

export function trackEvent(event: string, properties: Record<string, unknown> = {}): void {
  captureEvent(event, properties, { $os: 'Windows', platform: 'windows' })
}

function captureEvent(
  event: string,
  properties: Record<string, unknown>,
  runtime: { $os: 'Windows' | 'Linux' | 'unknown'; platform: 'windows' | 'linux' | 'unknown' }
): void {
  const distinctId = auth.currentUser?.uid ?? 'anonymous'
  void fetch(`${POSTHOG_HOST}/i/v0/e/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key: POSTHOG_KEY,
      event,
      distinct_id: distinctId,
      properties: {
        ...properties,
        $lib: 'omi-windows',
        ...runtime
      }
    })
  }).catch(() => {
    // Analytics is best-effort — swallow network/auth failures silently.
  })
}

// Same event name + property shape the desktop app's AnalyticsManager sends.
export function trackHowDidYouHear(source: string): void {
  trackEvent('Onboarding How Did You Hear', { source, is_referral: source === 'Friend' })
}

const FUNNEL_PLANS = new Set([
  'basic',
  'plus',
  'unlimited',
  'unlimited_v2',
  'operator',
  'architect',
  'unknown'
])

const FUNNEL_SOURCES = new Set([
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
  'unknown'
])

function subscriptionPlanWire(raw: string | null | undefined): string {
  const value = raw?.trim() ?? ''
  if (value === 'free') return 'basic'
  if (value === 'pro') return 'unknown'
  return FUNNEL_PLANS.has(value) ? value : 'unknown'
}

function subscriptionIntervalWire(raw: string | null | undefined): string {
  const value = raw?.trim().toLowerCase() ?? ''
  // Year before month so a title that contains both words is not labeled monthly.
  if (
    value === 'year' ||
    value === 'yearly' ||
    value === 'annual' ||
    value.includes('year') ||
    value.includes('annual')
  ) {
    return 'year'
  }
  if (value === 'month' || value === 'monthly' || value.includes('month')) return 'month'
  return 'unknown'
}

function subscriptionSourceWire(raw: string | null | undefined): string {
  const value = raw?.trim() ?? ''
  return FUNNEL_SOURCES.has(value) ? value : 'unknown'
}

export function trackPaywallOpened(source: string, currentPlan: string): void {
  trackEvent('Paywall Opened', {
    source: subscriptionSourceWire(source),
    current_plan: subscriptionPlanWire(currentPlan)
  })
}

export function trackUpgradePlanSelected(
  plan: string,
  billingInterval: string,
  source: string
): void {
  trackPurchaseEvent('upgradeTapped', {
    plan: subscriptionPlanWire(plan),
    billing_interval: subscriptionIntervalWire(billingInterval),
    source
  })
  trackEvent('Upgrade Plan Selected', {
    plan: subscriptionPlanWire(plan),
    billing_interval: subscriptionIntervalWire(billingInterval),
    source: subscriptionSourceWire(source)
  })
}

export function trackUpgradeSucceeded(plan: string, billingInterval: string): void {
  const properties = {
    plan: subscriptionPlanWire(plan),
    billing_interval: subscriptionIntervalWire(billingInterval)
  }
  trackEvent('Upgrade Succeeded Attributed', properties)
  trackEvent('Upgrade Succeeded')
}

export function trackUpgradeCancelled(): void {
  trackEvent('Upgrade Cancelled')
}

export function trackPurchaseEvent(id: PurchaseEventId, raw: Record<string, unknown>): void {
  const { name, properties } = purchasePayload(id, raw)
  try {
    // The preload reports process.platform. Never label a missing/other runtime as Windows.
    const platform = typeof window === 'undefined' ? undefined : window.electron?.process?.platform
    captureEvent(name, properties, {
      $os: platform === 'win32' ? 'Windows' : platform === 'linux' ? 'Linux' : 'unknown',
      platform: platform === 'win32' ? 'windows' : platform === 'linux' ? 'linux' : 'unknown'
    })
  } catch {
    /* Telemetry never changes purchase behavior. */
  }
}

/** `opened` comes from the main window ready-to-show IPC, never invocation intent. */
export async function openSubscriptionCheckout(
  open: (
    url: string,
    onOpened?: () => void,
    onCompleted?: () => void
  ) => Promise<'success' | 'cancel' | 'closed'>,
  url: string,
  plan: string,
  interval: string,
  source: string
) {
  const properties = {
    plan: subscriptionPlanWire(plan),
    billing_interval: subscriptionIntervalWire(interval),
    source,
    stage: 'in_app_checkout'
  }
  let reported = false
  let terminal = false
  let verifiedCompletion = false
  let outcome: 'success' | 'cancel' | 'closed'
  try {
    outcome = await open(
      url,
      () => {
        if (reported || terminal) return
        reported = true
        trackPurchaseEvent('checkoutOpened', { ...properties, result: 'opened' })
      },
      () => {
        if (!terminal && reported) verifiedCompletion = true
      }
    )
  } finally {
    terminal = true
  }
  if (outcome === 'success' && reported && verifiedCompletion)
    trackPurchaseEvent('checkoutCompleted', {
      ...properties,
      result: 'client_navigation_completed'
    })
  return outcome
}
