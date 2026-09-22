import { Request, Response } from 'express';
import { shopify_api_request } from '../api/shopifyApi';
import { sanitiseError, logInternalError } from '../utils/errorHandler';

export async function tool_get_order_details(req: Request, res: Response) {
  try {
    const { token, orderId } = req.body;
    const data = await shopify_api_request({
      endpoint: `/admin/api/2023-04/orders/${orderId}.json`,
      token,
    });
    res.json({ success: true, order: data.order });
  } catch (err) {
    logInternalError(err, 'tool_get_order_details');
    const safe = sanitiseError(err);
    res.status(500).json({ success: false, error: safe.message });
  }
}
