// Mirrors the macOS desktop app's PostHogManager: best-effort analytics sent to
// the same PostHog project via its HTTP ingestion API (no SDK needed). The project
// key is a publishable client key — safe to embed, exactly as the desktop app
// hardcodes it. Every call is fire-and-forget and never blocks or surfaces errors.
import { auth } from './firebase'
import { getWindowsDeviceIdHash } from './clientDevice'
import type { SignInProvider } from '../../../shared/types'

// Host is intentionally fixed to the CSP connect-src allowlist in renderer HTML.
// A VITE_POSTHOG_HOST override would silently fail under Chromium if it diverged.
const POSTHOG_HOST = 'https://us.i.posthog.com'
const POSTHOG_KEY =
  (import.meta.env.VITE_POSTHOG_KEY as string) || 'phc_z3qUFhGUgYIOMYnfxVSrLmYISQvbgph8iREQv3sez3Y'

let appVersionPromise: Promise<string | null> | null = null
let anonymousDistinctIdPromise: Promise<string> | null = null
const ANONYMOUS_ID_STORAGE_KEY = 'omi.posthog.anonymousDistinctId'

function getAppVersion(): Promise<string | null> {
  if (appVersionPromise) return appVersionPromise
  appVersionPromise =
    typeof window !== 'undefined' && window.omi?.getAppVersion
      ? window.omi
          .getAppVersion()
          .then(({ version }) => version || null)
          .catch(() => null)
      : Promise.resolve(null)
  return appVersionPromise
}

function getAnonymousDistinctId(): Promise<string> {
  if (anonymousDistinctIdPromise) return anonymousDistinctIdPromise
  try {
    const stored = window.localStorage?.getItem(ANONYMOUS_ID_STORAGE_KEY)
    if (stored) {
      anonymousDistinctIdPromise = Promise.resolve(stored)
      return anonymousDistinctIdPromise
    }
  } catch {
    // Storage is optional; the module cache still keeps the ID stable this run.
  }
  anonymousDistinctIdPromise = getWindowsDeviceIdHash()
    .then((hash) => `windows_${hash}`)
    .catch(() => `windows_${crypto.randomUUID()}`)
    .then((distinctId) => {
      try {
        window.localStorage?.setItem(ANONYMOUS_ID_STORAGE_KEY, distinctId)
      } catch {
        // Best-effort persistence only.
      }
      return distinctId
    })
  return anonymousDistinctIdPromise
}

function rotateAnonymousDistinctId(): void {
  const distinctId = `windows_${crypto.randomUUID()}`
  anonymousDistinctIdPromise = Promise.resolve(distinctId)
  try {
    window.localStorage?.setItem(ANONYMOUS_ID_STORAGE_KEY, distinctId)
  } catch {
    // Best-effort persistence only.
  }
}

function getDistinctId(): Promise<string> {
  return auth.currentUser?.uid ? Promise.resolve(auth.currentUser.uid) : getAnonymousDistinctId()
}

function captureEvent(
  event: string,
  properties: Record<string, unknown>,
  distinctId: Promise<string>
): void {
  // Calls register on one cached version promise, so capture order stays stable
  // while context resolves without serializing the independent network requests.
  void Promise.all([getAppVersion(), distinctId])
    .then(([appVersion, resolvedDistinctId]) =>
      fetch(`${POSTHOG_HOST}/i/v0/e/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: POSTHOG_KEY,
          event,
          distinct_id: resolvedDistinctId,
          properties: {
            ...properties,
            $lib: 'omi-windows',
            $os: 'Windows',
            platform: 'windows',
            ...(appVersion ? { app_version: appVersion } : {})
          }
        })
      })
    )
    .catch(() => {
      // Analytics is best-effort — swallow context, serialization and network failures.
    })
}

export function trackEvent(event: string, properties: Record<string, unknown> = {}): void {
  captureEvent(event, properties, getDistinctId())
}

// Same event name + property shape the desktop app's AnalyticsManager sends.
export function trackHowDidYouHear(source: string): void {
  const allowed = new Set([
    'Other',
    'Colleague',
    'Product Hunt',
    'Article',
    'Friend',
    'Event',
    'AI chat',
    'YouTube',
    'Search engine',
    'Newsletter',
    'Podcast',
    'Social media'
  ])
  const boundedSource = allowed.has(source) ? source : 'unknown'
  trackEvent('Onboarding How Did You Hear', {
    source: boundedSource,
    is_referral: boundedSource === 'Friend'
  })
}

export function trackOnboardingCompleted(): void {
  trackEvent('Onboarding Completed')
}

export type WindowsOnboardingStep =
  | 'Name'
  | 'Language'
  | 'HowDidYouHear'
  | 'Trust'
  | 'BackgroundPrivacy'
  | 'ScreenCaptureOptIn'
  | 'BuildProfile'
  | 'Microphone'
  | 'Automation'
  | 'ShortcutSetup'
  | 'VoiceIntro'
  | 'AskDemo'
  | 'DataSources'
  | 'Goal'

export function trackOnboardingStepCompleted(
  step: number,
  stepName: WindowsOnboardingStep,
  skipped: boolean
): void {
  const outcomeName = skipped ? `${stepName}_Skipped` : stepName
  trackEvent(`Onboarding Step ${outcomeName} Completed`, { step: Math.max(0, Math.floor(step)) })
}

export function trackSignInStarted(provider: SignInProvider): void {
  trackEvent('Sign In Started', { provider })
}

export function trackSignInCompleted(provider: SignInProvider): void {
  const uid = auth.currentUser?.uid
  if (!uid) {
    trackEvent('Sign In Completed', { provider })
    return
  }

  // The direct-ingestion equivalent of PostHog identify(): merge the stable,
  // pre-auth install identity into the Firebase uid before recording success.
  void getAnonymousDistinctId().then((anonymousDistinctId) => {
    captureEvent('$identify', { $anon_distinct_id: anonymousDistinctId }, Promise.resolve(uid))
    captureEvent('Sign In Completed', { provider }, Promise.resolve(uid))
  })
}

type SignInErrorClass =
  | 'cancelled'
  | 'superseded'
  | 'state_mismatch'
  | 'provider_rejected'
  | 'browser_open_failed'
  | 'token_exchange_failed'
  | 'unknown'

function signInErrorClass(error: unknown): SignInErrorClass {
  const message = (error instanceof Error ? error.message : String(error)).toLowerCase()
  if (message.includes('cancelled') || message.includes('never completed')) return 'cancelled'
  if (message.includes('superseded')) return 'superseded'
  if (message.includes('state mismatch')) return 'state_mismatch'
  if (message.includes('access_denied') || message.includes('provider rejected')) {
    return 'provider_rejected'
  }
  if (message.includes('could not open the browser')) return 'browser_open_failed'
  if (message.includes('token exchange') || message.includes('custom token')) {
    return 'token_exchange_failed'
  }
  return 'unknown'
}

export function trackSignInFailed(provider: SignInProvider, error: unknown): void {
  const errorClass = signInErrorClass(error)
  // Match macOS's bounded schema: the historical `error` property is a class,
  // never the raw OAuth/Firebase message (which can contain account data).
  trackEvent('Sign In Failed', { provider, error: errorClass, error_class: errorClass })
}

export function trackSignedOut(distinctId: string): void {
  // The Firebase user is already gone once signOutUser resolves. Carry only the
  // previously captured uid as PostHog identity; it is never an event property.
  captureEvent(
    'Signed Out',
    {},
    distinctId ? Promise.resolve(distinctId) : getAnonymousDistinctId()
  )
  // Match PostHog reset semantics: a shared Windows installation must not reuse
  // one person's merged anonymous ID if another account signs in later.
  rotateAnonymousDistinctId()
}

export type WindowsPermission = 'microphone' | 'screen_capture_opt_in' | 'automation_consent'

export function trackPermissionRequested(permission: WindowsPermission): void {
  trackEvent('Permission Requested', { permission })
}

export function trackPermissionGranted(permission: WindowsPermission): void {
  trackEvent('Permission Granted', { permission })
}

export function trackPermissionDenied(permission: WindowsPermission): void {
  trackEvent('Permission Denied', { permission })
}

export function trackPermissionSkipped(permission: WindowsPermission): void {
  trackEvent('Permission Skipped', { permission })
}

export function trackMemoryCreated(durationSeconds: number): void {
  trackEvent('Memory Created', {
    source: 'desktop',
    duration_seconds: Math.max(0, Math.floor(durationSeconds))
  })
}

export type WindowsChatSource = 'desktop_chat' | 'desktop_voice'

export function trackChatMessageSent(properties: {
  messageLength: number
  hasSelectedAppContext: boolean
  source: WindowsChatSource
}): void {
  trackEvent('Chat Message Sent', {
    message_length: Math.max(0, Math.floor(properties.messageLength)),
    has_selected_app_context: properties.hasSelectedAppContext,
    source: properties.source
  })
}

export function trackPageViewed(page: string): void {
  // `page` comes from the closed route manifest, never a raw pathname carrying IDs.
  trackEvent('Page Viewed', { page })
}

function boundedAppDimension(value?: string | null): string {
  if (!value) return 'unknown'
  const normalized = value
    .toLowerCase()
    .replace(/[^a-z0-9._:-]/g, '_')
    .slice(0, 80)
  return normalized || 'unknown'
}

function appProperties(appId: string, category?: string | null): Record<string, string> {
  return {
    app_id: boundedAppDimension(appId),
    category: boundedAppDimension(category)
  }
}

export function trackAppEnabled(appId: string, category?: string | null): void {
  trackEvent('App Enabled', appProperties(appId, category))
}

export function trackAppDisabled(appId: string, category?: string | null): void {
  trackEvent('App Disabled', appProperties(appId, category))
}

export function trackAppDetailViewed(appId: string, category?: string | null): void {
  trackEvent('App Detail Viewed', appProperties(appId, category))
}
