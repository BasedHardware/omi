import { Request, Response } from 'express';
import { shopify_api_request } from '../api/shopifyApi';
import { sanitiseError, logInternalError } from '../utils/errorHandler';

export async function tool_get_orders(req: Request, res: Response) {
  try {
    const { token, limit = 20 } = req.body;
    const data = await shopify_api_request({
      endpoint: `/admin/api/2023-04/orders.json?limit=${limit}`,
      token,
    });
    res.json({ success: true, orders: data.orders });
  } catch (err) {
    logInternalError(err, 'tool_get_orders');
    const safe = sanitiseError(err);
    res.status(500).json({ success: false, error: safe.message });
  }
}
