// PII scrubbing for Sentry events. Strips email addresses out of the
// human-readable text fields (message + exception values) before an event leaves
// the app. Shared by BOTH the renderer (renderer/main.tsx) and the main process
// (main/sentry.ts) so the two Sentry inits scrub identically. Kept dependency-free
// (a structural event type, not Sentry's) so it's cheap to unit-test. Not
// exhaustive — a best-effort guard against the most common leak (emails in error
// strings), not a full redactor.

const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g

/** Replace any email-looking substrings with a placeholder. */
export function scrubEmails(text: string): string {
  return text.replace(EMAIL_RE, '[email]')
}

// The subset of a Sentry event we touch. Loosely typed so we don't depend on the
// SDK's types here (Sentry's Event is structurally compatible at the call site).
type ScrubbableEvent = {
  message?: string
  exception?: { values?: Array<{ value?: string }> }
  request?: { url?: string; query_string?: unknown; headers?: Record<string, unknown> }
  breadcrumbs?: Array<{ message?: string; data?: Record<string, unknown> }>
  extra?: Record<string, unknown>
}

const SECRET_KEY_RE = /^(authorization|cookie|set-cookie|password|secret|token|api[-_]?key)$/i
const URL_KEY_RE = /^(url|uri|href|link)$/i

function scrubUrl(raw: string): string {
  try {
    const url = new URL(raw)
    url.username = ''
    url.password = ''
    url.search = ''
    url.hash = ''
    return url.toString()
  } catch {
    return scrubEmails(raw)
  }
}

function scrubNested(value: unknown, key = '', seen = new WeakSet<object>()): unknown {
  if (SECRET_KEY_RE.test(key)) return '[redacted]'
  if (typeof value === 'string') {
    return URL_KEY_RE.test(key) ? scrubUrl(value) : scrubEmails(value)
  }
  if (!value || typeof value !== 'object' || seen.has(value)) return value
  seen.add(value)
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) value[i] = scrubNested(value[i], '', seen)
    return value
  }
  for (const [nestedKey, nestedValue] of Object.entries(value)) {
    ;(value as Record<string, unknown>)[nestedKey] = scrubNested(nestedValue, nestedKey, seen)
  }
  return value
}

/**
 * Scrub emails from an event's message and exception values in place, returning
 * the same object. Safe to hand directly to Sentry's `beforeSend`.
 */
export function scrubEventPii<T extends ScrubbableEvent>(event: T): T {
  if (typeof event.message === 'string') {
    event.message = scrubEmails(event.message)
  }
  const values = event.exception?.values
  if (Array.isArray(values)) {
    for (const v of values) {
      if (typeof v.value === 'string') v.value = scrubEmails(v.value)
    }
  }
  if (event.request) {
    if (typeof event.request.url === 'string') event.request.url = scrubUrl(event.request.url)
    delete event.request.query_string
    if (event.request.headers) scrubNested(event.request.headers)
  }
  if (event.breadcrumbs) scrubNested(event.breadcrumbs)
  if (event.extra) scrubNested(event.extra)
  return event
}
