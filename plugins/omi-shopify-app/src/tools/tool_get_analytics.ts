import { Request, Response } from 'express';
import { shopify_api_request } from '../api/shopifyApi';
import { sanitiseError, logInternalError } from '../utils/errorHandler';

/**
 * GET /shopify/analytics
 *
 * Returns basic analytics data from Shopify.
 * All internal errors are now sanitised before being sent to the client.
 */
export async function tool_get_analytics(req: Request, res: Response) {
  try {
    const { token } = req.body; // token should be validated upstream
    const data = await shopify_api_request({
      endpoint: '/admin/api/2023-04/shop.json',
      token,
    });
    res.json({ success: true, data });
  } catch (err) {
    // err is already a SanitisedError from shopify_api_request, but we guard
    // against any unexpected shape.
    logInternalError(err, 'tool_get_analytics');
    const safe = sanitiseError(err);
    res.status(500).json({ success: false, error: safe.message });
  }
}
