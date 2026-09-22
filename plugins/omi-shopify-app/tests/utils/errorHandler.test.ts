import { sanitiseError } from '../../src/utils/errorHandler';

describe('sanitiseError', () => {
  it('returns safe message when error has a user‑friendly message', () => {
    const err = new Error('Invalid input provided');
    const result = sanitiseError(err);
    expect(result.message).toBe('Invalid input provided');
  });

  it('hides stack traces and internal details', () => {
    const err = new Error('Something went wrong\n    at Object.<anonymous> (index.js:10:15)');
    const result = sanitiseError(err);
    expect(result.message).not.toContain('at Object');
    expect(result.message).toBe('An unexpected error occurred. Please try again later.');
  });

  it('maps known Shopify HTTP status codes to friendly messages', () => {
    const err: any = new Error('Shopify API error 401: Unauthorized');
    err.response = { status: 401, body: 'Unauthorized' };
    const result = sanitiseError(err);
    expect(result.message).toBe('Authentication with Shopify failed.');
  });

  it('falls back to generic message for unknown errors', () => {
    const result = sanitiseError('string error');
    expect(result.message).toBe('An unexpected error occurred. Please try again later.');
  });
});
