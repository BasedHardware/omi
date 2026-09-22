import { Request, Response } from 'express';
import { shopify_api_request } from '../api/shopifyApi';
import { sanitiseError, logInternalError } from '../utils/errorHandler';

export async function tool_create_customer(req: Request, res: Response) {
  try {
    const { token, customerPayload } = req.body;
    const data = await shopify_api_request({
      endpoint: '/admin/api/2023-04/customers.json',
      method: 'POST',
      token,
      body: customerPayload,
    });
    res.json({ success: true, customer: data.customer });
  } catch (err) {
    logInternalError(err, 'tool_create_customer');
    const safe = sanitiseError(err);
    res.status(500).json({ success: false, error: safe.message });
  }
}
