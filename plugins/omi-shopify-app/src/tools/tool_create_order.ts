import { Request, Response } from 'express';
import { shopify_api_request } from '../api/shopifyApi';
import { sanitiseError, logInternalError } from '../utils/errorHandler';

export async function tool_create_order(req: Request, res: Response) {
  try {
    const { token, orderPayload } = req.body;
    const data = await shopify_api_request({
      endpoint: '/admin/api/2023-04/orders.json',
      method: 'POST',
      token,
      body: orderPayload,
    });
    res.json({ success: true, order: data.order });
  } catch (err) {
    logInternalError(err, 'tool_create_order');
    const safe = sanitiseError(err);
    res.status(500).json({ success: false, error: safe.message });
  }
}
