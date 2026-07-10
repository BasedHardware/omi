// Main-process crash/error reporting. Fully opt-in: with no DSN configured
// (MAIN_VITE_SENTRY_DSN unset) this is a no-op, so dev and self-builds report
// nothing. Reporting is only enabled for packaged builds. The renderer wires its
// own Sentry init separately.
import { app } from 'electron'
import * as Sentry from '@sentry/electron/main'

// Redact obvious secrets/PII before an event leaves the machine: strip
// Authorization headers and drop the user's email from the user context.
function scrub<T extends Sentry.Event>(event: T): T {
  const headers = event.request?.headers as Record<string, string> | undefined
  if (headers) {
    for (const key of Object.keys(headers)) {
      if (key.toLowerCase() === 'authorization' || key.toLowerCase() === 'cookie') {
        headers[key] = '[redacted]'
      }
    }
  }
  if (event.user && 'email' in event.user) delete event.user.email
  return event
}

let initialized = false

export function initSentry(): void {
  if (initialized) return
  const dsn = import.meta.env.MAIN_VITE_SENTRY_DSN
  if (!dsn) return // no DSN → reporting disabled entirely
  initialized = true

  Sentry.init({
    dsn,
    enabled: app.isPackaged,
    environment: app.isPackaged ? 'production' : 'development',
    release: app.getVersion(),
    beforeSend: (event) => scrub(event)
  })
}
