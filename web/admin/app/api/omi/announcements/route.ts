import { NextResponse } from 'next/server';
import { verifyFirebaseToken } from '@/lib/firebase/admin';

export const dynamic = 'force-dynamic';

const OMI_API_URL = process.env.NEXT_PUBLIC_OMI_API_URL;
const OMI_SECRET_KEY = process.env.OMI_API_SECRET_KEY;

async function verifyAuth(request: Request) {
  const authorization = request.headers.get('Authorization');
  if (!authorization || !authorization.startsWith('Bearer ')) {
    return null;
  }
  const token = authorization.split('Bearer ')[1];
  return verifyFirebaseToken(token);
}

// GET /api/omi/announcements - List all announcements
export async function GET(request: Request) {
  const decoded = await verifyAuth(request);
  if (!decoded) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const url = new URL(request.url);
    const type = url.searchParams.get('type');
    const activeOnly = url.searchParams.get('active_only') === 'true';

    let apiUrl = `${OMI_API_URL}/v1/announcements/all?`;
    if (type) apiUrl += `type=${type}&`;
    if (activeOnly) apiUrl += `active_only=true&`;

    const res = await fetch(apiUrl, {
      headers: {
        'secret-key': OMI_SECRET_KEY!,
      },
      cache: 'no-store',
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Backend error: ${res.status} ${text}`);
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: any) {
    console.error('[announcements GET] Error:', err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}

// POST /api/omi/announcements - Create announcement
export async function POST(request: Request) {
  const decoded = await verifyAuth(request);
  if (!decoded) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const body = await request.json();

    const res = await fetch(`${OMI_API_URL}/v1/announcements`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'secret-key': OMI_SECRET_KEY!,
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Backend error: ${res.status} ${text}`);
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: any) {
    console.error('[announcements POST] Error:', err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}
