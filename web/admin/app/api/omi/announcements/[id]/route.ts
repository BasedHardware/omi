import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';

export const dynamic = 'force-dynamic';

const OMI_API_URL = process.env.NEXT_PUBLIC_OMI_API_URL;
const OMI_SECRET_KEY = process.env.OMI_API_SECRET_KEY;

// GET /api/omi/announcements/[id] - Get single announcement
export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const res = await fetch(`${OMI_API_URL}/v1/announcements/${params.id}`, {
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
    console.error('[announcements GET id] Error:', err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}

// PUT /api/omi/announcements/[id] - Update announcement
export async function PUT(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const body = await request.json();

    const res = await fetch(`${OMI_API_URL}/v1/announcements/${params.id}`, {
      method: 'PUT',
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
    console.error('[announcements PUT] Error:', err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}

// DELETE /api/omi/announcements/[id] - Delete announcement
export async function DELETE(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const url = new URL(request.url);
    const hardDelete = url.searchParams.get('hard') === 'true';

    const res = await fetch(
      `${OMI_API_URL}/v1/announcements/${params.id}?soft_delete=${!hardDelete}`,
      {
        method: 'DELETE',
        headers: {
          'secret-key': OMI_SECRET_KEY!,
        },
      }
    );

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Backend error: ${res.status} ${text}`);
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: any) {
    console.error('[announcements DELETE] Error:', err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}
