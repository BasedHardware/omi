/**
 * Utility to sanitize error messages before exposing them to the user.
 *
 * The goal is to avoid leaking stack traces or internal details that may
 * contain sensitive information.  We only expose the error message itself.
 */
export function sanitizeErrorMessage(err: unknown): string {
  if (err instanceof Error) {
    return err.message;
  }

  if (typeof err === 'string') {
    return err;
  }

  if (
    err &&
    typeof err === 'object' &&
    'message' in err &&
    typeof (err as any).message === 'string'
  ) {
    return (err as any).message;
  }

  return String(err);
}
