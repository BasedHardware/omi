/**
 * Utility functions for the omi-crossref-app plugin.
 *
 * This module currently provides a single helper to sanitize error
 * messages that are exposed to the user.  The goal is to avoid leaking
 * raw exception details (stack traces, internal URLs, etc.) in the
 * `ChatToolResponse.error` field.
 */

export function sanitizeError(err: unknown): string {
  // If we have a proper Error instance, use its message.
  if (err instanceof Error) {
    // Strip any non-printable or control characters that might
    // interfere with JSON serialization or display.
    return err.message.replace(/[^\x20-\x7E]/g, '');
  }

  // Fallback: convert to string and strip non-printable characters.
  return String(err).replace(/[^\x20-\x7E]/g, '');
}
