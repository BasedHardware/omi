import { Request, Response, NextFunction } from 'express';
import { logger } from '../../utils/logger';

/**
 * Generic error handling middleware that logs the error and returns a
 * sanitized, user‑friendly message to the client.  It also ensures that
 * no raw exception text or upstream HTTP bodies are leaked into the
 * response or into any LLM context.
 */
export function errorHandler(
  err: unknown,
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // Log the full error for internal diagnostics
  logger.error('Unhandled error in request %s %s', req.method, req.originalUrl, err);

  // Determine a safe status code
  const status = (err as any)?.status || 500;

  // Build a generic error message
  const message =
    status === 500
      ? 'An unexpected error occurred. Please try again later.'
      : 'An error occurred. Please check your request and try again.';

  // Send a sanitized JSON response
  res.status(status).json({ error: message });
}
