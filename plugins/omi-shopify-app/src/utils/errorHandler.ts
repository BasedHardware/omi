/**
 * Utility helpers for sanitising errors that are exposed to the client.
 *
 * The Shopify plugin previously leaked internal exception messages and stack
 * traces via `console.error` and direct error propagation. This module provides
 * a single source of truth for how errors are transformed before being sent
 * back to the caller.
 */

export interface SanitisedError {
  /** Human‑readable message safe for external consumption */
  message: string;
  /** Optional error code for internal routing (not exposed to the client) */
  code?: string;
}

/**
 * Determines whether an error object contains a safe, user‑facing message.
 *
 * @param err - The caught error (could be anything)
 * @returns true if the error has a non‑technical message we can expose
 */
function isSafeMessage(err: unknown): err is { message: string } {
  return (
    typeof err === 'object' &&
    err !== null &&
    'message' in err &&
    typeof (err as any).message === 'string' &&
    // Heuristic: avoid exposing stack traces or internal identifiers
    !(err as any).message.toLowerCase().includes('stack') &&
    !(err as any).message.toLowerCase().includes('error:') // generic fallback
  );
}

/**
 * Convert any thrown value into a sanitised error object.
 *
 * - If the error already contains a safe message, use it.
 * - Otherwise, return a generic message that does not reveal internal details.
 *
 * @param err - The caught error
 * @returns SanitisedError ready to be sent to the client
 */
export function sanitiseError(err: unknown): SanitisedError {
  if (isSafeMessage(err)) {
    return { message: err.message };
  }

  // Known Shopify API errors have a `response` field with status & body.
  if (
    typeof err === 'object' &&
    err !== null &&
    'response' in err &&
    typeof (err as any).response === 'object' &&
    (err as any).response !== null &&
    'status' in (err as any).response
  ) {
    const status = (err as any).response.status;
    // Provide a user‑friendly message based on HTTP status
    if (status === 401) {
      return { message: 'Authentication with Shopify failed.' };
    }
    if (status === 404) {
      return { message: 'Requested resource not found on Shopify.' };
    }
    return { message: 'Shopify request failed. Please try again later.' };
  }

  // Fallback generic message
  return { message: 'An unexpected error occurred. Please try again later.' };
}

/**
 * Centralised logger for internal errors.
 *
 * This logs the full error (including stack trace) to the server console
 * while ensuring the client never sees it.
 *
 * @param err - The caught error
 * @param context - Optional context string to help locate the source
 */
export function logInternalError(err: unknown, context?: string): void {
  const prefix = context ? `[Shopify Plugin] ${context}: ` : '[Shopify Plugin] ';
  // eslint-disable-next-line no-console
  console.error(prefix, err);
}
