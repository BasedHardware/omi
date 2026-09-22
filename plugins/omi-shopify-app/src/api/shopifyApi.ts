import fetch from 'node-fetch';
import { sanitiseError, logInternalError } from '../utils/errorHandler';

/**
 * Performs a request against the Shopify REST API.
 *
 * Previously this function bubbled raw errors (including stack traces) to the
 * caller, which caused internal exception leaks. The implementation now
 * catches any error, logs the full details internally, and returns a
 * sanitised error payload.
 *
 * @param endpoint - Relative Shopify API endpoint (e.g. `/admin/api/2023-04/orders.json`)
 * @param method - HTTP method
 * @param token - Shopify access token
 * @param body - Optional request body
 * @returns JSON response from Shopify
 * @throws SanitisedError – a safe error object for the caller
 */
export async function shopify_api_request<T = any>(params: {
  endpoint: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  token: string;
  body?: unknown;
}): Promise<T> {
  const { endpoint, method = 'GET', token, body } = params;
  const url = `https://${process.env.SHOPIFY_STORE_DOMAIN}${endpoint}`;

  try {
    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Shopify-Access-Token': token,
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const errorBody = await response.text();
      const err = new Error(
        `Shopify API error ${response.status}: ${errorBody}`
      );
      // Attach response for downstream sanitisation logic
      (err as any).response = { status: response.status, body: errorBody };
      throw err;
    }

    const data = (await response.json()) as T;
    return data;
  } catch (err) {
    // Log the full error internally (including stack trace)
    logInternalError(err, `shopify_api_request ${endpoint}`);
    // Throw a sanitised version for the outer layer
    const safe = sanitiseError(err);
    // Preserve the shape expected by callers (they catch and read .message)
    throw safe;
  }
}
