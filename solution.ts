/**
 * Utility helpers for sanitising error messages that are sent back to the client.
 * The goal is to avoid leaking internal stack traces or sensitive information.
 */

export class SanitizedError extends Error {
  constructor(public readonly userMessage: string) {
    super(userMessage);
    // Preserve proper prototype chain (required when targeting ES5)
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Convert any thrown value into a SanitizedError.
 * If the value is already a SanitizedError we keep its userMessage,
 * otherwise we return a generic message.
 */
export function sanitizeError(err: unknown): SanitizedError {
  if (err instanceof SanitizedError) {
    return err;
  }

  // If the error looks like a normal Error we can keep its message
  // but we never expose stack traces or internal details.
  if (err instanceof Error) {
    return new SanitizedError(err.message || 'An unexpected error occurred');
  }

  // Fallback for non‑Error throws
  return new SanitizedError('An unexpected error occurred');
}
