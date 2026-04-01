import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
export const dynamic = 'force-dynamic';

const OMI_API_BASE_URL = process.env.NEXT_PUBLIC_OMI_API_URL;
const OMI_API_SECRET_KEY_BASE = process.env.OMI_API_SECRET_KEY;

export async function POST(req: NextRequest, { params }: { params: { app_id: string } }) {
  const authResult = await verifyAdmin(req);
  if (authResult instanceof NextResponse) return authResult;

  if (!OMI_API_BASE_URL) {
    return NextResponse.json({ error: 'OMI API base URL not configured' }, { status: 500 });
  }
  if (!OMI_API_SECRET_KEY_BASE) {
    return NextResponse.json({ error: 'OMI API secret key not configured' }, { status: 500 });
  }

  try {
    const incomingForm = await req.formData();

    // Validate required fields
    const appId = (incomingForm.get('app_id') as string) || params.app_id;
    const uid = (incomingForm.get('uid') as string) || '';
    if (!appId) {
      return NextResponse.json({ error: 'app_id is required' }, { status: 400 });
    }
    if (!uid) {
      return NextResponse.json({ error: 'uid is required' }, { status: 400 });
    }

    // Ensure app_id in body matches path param if present
    if (params.app_id && appId !== params.app_id) {
      return NextResponse.json({ error: 'app_id mismatch' }, { status: 400 });
    }

    // Transform incoming fields into FastAPI expected shape: app_data (json string) + optional file
    // Collect fields into a plain object
    const data: Record<string, any> = {};
    let fileBlob: any = null;
    incomingForm.forEach((value, key) => {
      const isBlob = typeof value === 'object' && value !== null && typeof (value as any).arrayBuffer === 'function';
      if (key === 'image' && isBlob) {
        fileBlob = value;
        return;
      }
      if (key === 'app_id') return; // we already have appId
      if (key === 'uid' && typeof value === 'string') {
        data['uid'] = value;
        return;
      }
      // Normalize known fields
      if (typeof value === 'string') {
        switch (key) {
          case 'name':
          case 'description':
          case 'memory_prompt':
          case 'chat_prompt':
          case 'persona_prompt':
          case 'category':
          case 'payment_plan':
          case 'payment_product_id':
          case 'payment_price_id':
          case 'payment_link_id':
          case 'payment_link':
          case 'author':
            data[key] = value;
            return;
          case 'image_url':
            // If a direct URL was provided, map to image field (will be overridden by file if present)
            data['image'] = value;
            return;
          case 'price':
            data['price'] = value === '' ? undefined : Number(value);
            return;
          case 'is_paid':
          case 'private':
          case 'enabled':
            data[key] = value === 'true' || value === '1';
            return;
          default:
            // Pass through unknown scalar fields as-is
            data[key] = value;
            return;
        }
      }
    });

    // Ensure id present
    data['id'] = appId;

    // Build outbound multipart
    const outbound = new FormData();
    outbound.append('app_data', JSON.stringify(data));
    if (fileBlob) {
      const filename = (fileBlob as any).name || 'upload';
      outbound.append('file', fileBlob as any, filename);
    }

    // Authorization header: Bearer secret_key+uid
    const authHeaderValue = `${OMI_API_SECRET_KEY_BASE}${uid}`;

    // FastAPI endpoint path: PATCH /v1/apps/{app_id}
    const url = `${OMI_API_BASE_URL}/v1/apps/${appId}`;

    const res = await fetch(url, {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${authHeaderValue}`,
        // DO NOT set Content-Type for multipart; let fetch set boundary
      },
      body: outbound,
      // Route runs on server, outbound fetch is server-side
    });

    const text = await res.text();
    let json: any = null;
    try {
      json = text ? JSON.parse(text) : {};
    } catch {
      json = { message: text };
    }

    if (!res.ok) {
      return NextResponse.json({ error: json?.detail || json?.error || 'Update failed' }, { status: res.status });
    }

    return NextResponse.json(json || { ok: true });
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || 'Unexpected error' }, { status: 500 });
  }
}


