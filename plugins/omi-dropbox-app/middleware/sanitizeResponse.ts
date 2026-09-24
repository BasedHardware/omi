import { Request, Response, NextFunction } from 'express';

/**
 * Middleware that sanitizes any stringified error messages that might
 * accidentally be sent back to the client.  It replaces any occurrence
 * of the word "error" in the response body with a generic placeholder.
 */
export function sanitizeResponse(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const originalSend = res.send;
  res.send = function (body?: any): Response {
    if (typeof body === 'string' && body.toLowerCase().includes('error')) {
      body = 'An error occurred. Please try again.';
    }
    return originalSend.call(this, body);
  };
  next();
}
