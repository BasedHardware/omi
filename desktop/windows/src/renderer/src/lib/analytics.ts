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

let appVersionPromise: Promise<string | null> | null = null

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

export function trackEvent(event: string, properties: Record<string, unknown> = {}): void {
  const distinctId = auth.currentUser?.uid ?? 'anonymous'
  // Calls register on one cached version promise, so capture order stays stable
  // while context resolves without serializing the independent network requests.
  void getAppVersion().then((appVersion) =>
    fetch(`${POSTHOG_HOST}/i/v0/e/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: POSTHOG_KEY,
        event,
        distinct_id: distinctId,
        properties: {
          ...properties,
          $lib: 'omi-windows',
          $os: 'Windows',
          platform: 'windows',
          ...(appVersion ? { app_version: appVersion } : {})
        }
      })
    }).catch(() => {
      // Analytics is best-effort — swallow network/auth failures silently.
    })
  )
}

// Same event name + property shape the desktop app's AnalyticsManager sends.
export function trackHowDidYouHear(source: string): void {
  trackEvent('Onboarding How Did You Hear', { source, is_referral: source === 'Friend' })
}
