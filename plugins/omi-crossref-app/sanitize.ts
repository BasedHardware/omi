/**
 * Utility to sanitize error messages before exposing them to the client.
 *
 * The goal is to prevent leaking sensitive information such as URLs,
 * stack traces, or internal identifiers.  The implementation is intentionally
 * conservative: it removes any HTTP(S) URLs and falls back to the error
 * message or string representation for other types.
 */

export function sanitizeError(err: unknown): string {
  if (typeof err === 'string') {
    // Remove any URLs that might contain secrets or internal data
    return err.replace(/https?:\/\/[^\s]+/g, '[REDACTED URL]');
  }

  if (err instanceof Error) {
    return err.message.replace(/https?:\/\/[^\s]+/g, '[REDACTED URL]');
  }

  // For any other type, use a safe string representation
  return String(err);
}
