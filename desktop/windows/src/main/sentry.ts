// Main-process crash/error reporting. Fully opt-in: with no DSN configured
// (MAIN_VITE_SENTRY_DSN unset) this is a no-op, so dev and self-builds report
// nothing. Reporting is only enabled for packaged builds. The renderer wires its
// own Sentry init separately.
import { app } from 'electron'
import * as Sentry from '@sentry/electron/main'
import { scrubEventPii } from '../shared/sentryScrub'

// Redact obvious secrets/PII before an event leaves the machine: strip
// Authorization/Cookie headers, drop the user's email from the user context, and
// scrub emails out of the message/exception text (the shared scrubber the
// renderer uses too).
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
  return scrubEventPii(event)
}

/** Report a non-fatal error the app healed from (e.g. database corruption
 *  recovery). No-ops when Sentry is not initialized/enabled, exactly like the
 *  crash path — so dev and self-builds still report nothing. Scrubbing is applied
 *  by the beforeSend hook above. */
export function captureError(
  err: unknown,
  context: { area: string; extra?: Record<string, unknown> }
): void {
  Sentry.captureException(err, {
    tags: { area: context.area },
    extra: context.extra
  })
}

/** Report a developer-facing telemetry MESSAGE (not an exception, no user banner):
 *  e.g. "a crash was detected on the previous launch", or "a renderer went
 *  unresponsive". No-ops when Sentry is not initialized/enabled, exactly like the
 *  exception path — so dev and self-builds report nothing. Scrubbing is applied by
 *  the beforeSend hook above. */
export function captureMessage(
  message: string,
  context: { area: string; level?: Sentry.SeverityLevel; extra?: Record<string, unknown> }
): void {
  Sentry.captureMessage(message, {
    level: context.level ?? 'info',
    tags: { area: context.area },
    extra: context.extra
  })
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
