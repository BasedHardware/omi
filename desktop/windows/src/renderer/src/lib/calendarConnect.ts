// Google Calendar via the BACKEND-mediated OAuth lane — needs NO client-side
// Google credentials (the backend holds GOOGLE_CLIENT_ID/SECRET and does the token
// exchange). Flow: GET the auth URL → open it in the system browser → the backend
// callback stores tokens and redirects to a hardcoded omi:// deep link the Windows
// build can't receive, so completion is detected by POLLING the integration status
// until {connected:true}. Only `google_calendar` is supported on this lane; Gmail
// stays on the separate client-side loopback lane.
import { omiApi } from './apiClient'

const OAUTH_URL_PATH = '/v1/integrations/google_calendar/oauth-url'
const STATUS_PATH = '/v1/integrations/google_calendar'

export type CalendarStatus = { connected: boolean; lastSyncAt?: string }

export async function getCalendarStatus(): Promise<CalendarStatus> {
  const r = await omiApi.get(STATUS_PATH)
  const d = (r.data ?? {}) as { connected?: boolean; last_synced?: string; last_synced_at?: string }
  return { connected: !!d.connected, lastSyncAt: d.last_synced ?? d.last_synced_at }
}

export async function getCalendarOAuthUrl(): Promise<string> {
  const r = await omiApi.get(OAUTH_URL_PATH)
  const url = (r.data as { auth_url?: string })?.auth_url
  if (!url) throw new Error('No auth URL returned by the server')
  return url
}

/** Disconnect the calendar integration (backend DELETE → 204, or 404 if absent). */
export async function disconnectCalendar(): Promise<void> {
  await omiApi.delete(STATUS_PATH)
}

/**
 * Poll a status getter until it reports connected, sleeping BEFORE each check
 * (the backend needs a beat after the browser hands back). Returns true on
 * connect, false on timeout/cancel. Transient status errors are swallowed so a
 * blip doesn't abort the wait. Pure (sleep + status injected) so it unit-tests
 * without real timers, and reused by the X connector's phase-1 poll.
 */
export async function pollUntilConnected(
  getStatus: () => Promise<{ connected: boolean }>,
  opts: {
    intervalMs: number
    maxAttempts: number
    sleep?: (ms: number) => Promise<void>
    /** Return true to cancel the wait (e.g. the user dismissed the panel). */
    canceled?: () => boolean
  }
): Promise<boolean> {
  const sleep = opts.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)))
  for (let i = 0; i < opts.maxAttempts; i++) {
    if (opts.canceled?.()) return false
    await sleep(opts.intervalMs)
    if (opts.canceled?.()) return false
    try {
      if ((await getStatus()).connected) return true
    } catch {
      /* transient — keep polling */
    }
  }
  return false
}
