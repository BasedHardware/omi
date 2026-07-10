// PII scrubbing for Sentry events sent from the renderer. Strips email addresses
// out of the human-readable text fields (message + exception values) before an
// event leaves the app. Kept dependency-free (a structural event type, not
// Sentry's) so it's cheap to unit-test. Not exhaustive — a best-effort guard
// against the most common leak (emails in error strings), not a full redactor.

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
  return event
}
