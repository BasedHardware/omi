import { Request, Response } from 'express';
import { shopify_api_request } from '../api/shopifyApi';
import { sanitiseError, logInternalError } from '../utils/errorHandler';

export async function tool_get_customers(req: Request, res: Response) {
  try {
    const { token, limit = 20 } = req.body;
    const data = await shopify_api_request({
      endpoint: `/admin/api/2023-04/customers.json?limit=${limit}`,
      token,
    });
    res.json({ success: true, customers: data.customers });
  } catch (err) {
    logInternalError(err, 'tool_get_customers');
    const safe = sanitiseError(err);
    res.status(500).json({ success: false, error: safe.message });
  }
}
