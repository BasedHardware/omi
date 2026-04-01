import { NextRequest, NextResponse } from 'next/server';
import admin, { getDb } from '@/lib/firebase/admin';
import { verifyAdmin } from '@/lib/auth';

export const dynamic = 'force-dynamic';

async function fetchSummaryAppIds(): Promise<string[]> {
  const baseUrl = process.env.NEXT_PUBLIC_OMI_API_URL;
  const secret = process.env.OMI_API_SECRET_KEY;
  if (!baseUrl || !secret) {
    throw new Error('OMI API env vars missing');
  }
  const res = await fetch(`${baseUrl}/v1/summary-app-ids`, {
    headers: {
      'secret-key': secret,
    },
    cache: 'no-store',
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to fetch summary app ids: ${res.status} ${text}`);
  }
  const data = await res.json();
  console.log('[summary-apps] data:', data);
  const ids: string[] = Array.isArray(data?.app_ids) ? data.app_ids : [];
  return ids;
}

async function fetchAppsByIds(ids: string[]) {
  const firestore = getDb();
  const collection = firestore.collection('plugins_data');
  const chunkSize = 10;
  const chunks: string[][] = [];
  for (let i = 0; i < ids.length; i += chunkSize) {
    chunks.push(ids.slice(i, i + chunkSize));
  }
  const allDocs: FirebaseFirestore.DocumentData[] = [];
  for (const chunk of chunks) {
    const snap = await collection
      .where(admin.firestore.FieldPath.documentId(), 'in', chunk)
      .get();
    snap.forEach((doc) => {
      allDocs.push({ id: doc.id, ...doc.data() });
    });
  }
  return allDocs;
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const ids = await fetchSummaryAppIds();
    if (ids.length === 0) {
      return NextResponse.json([]);
    }
    const apps = await fetchAppsByIds(ids);
    return NextResponse.json(apps);
  } catch (err: any) {
    console.error('[summary-apps] Error:', err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}

export async function PATCH(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const body = await request.json();
    const { appId, name, description, memory_prompt } = body;

    if (!appId) {
      return NextResponse.json({ error: 'App ID is required' }, { status: 400 });
    }

    const firestore = getDb();
    const appRef = firestore.collection('plugins_data').doc(appId);

    const updateData: any = {};
    if (name !== undefined) updateData.name = name;
    if (description !== undefined) updateData.description = description;
    if (memory_prompt !== undefined) updateData.memory_prompt = memory_prompt;

    await appRef.update(updateData);

    return NextResponse.json({ success: true });
  } catch (err: any) {
    console.error('[summary-apps PATCH] Error:', err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const body = await request.json();
    const { appId } = body;

    if (!appId) {
      return NextResponse.json({ error: 'App ID is required' }, { status: 400 });
    }

    const baseUrl = process.env.NEXT_PUBLIC_OMI_API_URL;
    const secret = process.env.OMI_API_SECRET_KEY;
    if (!baseUrl || !secret) {
      throw new Error('OMI API env vars missing');
    }

    const res = await fetch(`${baseUrl}/v1/summary-app-ids/${appId}`, {
      method: 'POST',
      headers: {
        'secret-key': secret,
      },
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Failed to add summary app: ${res.status} ${text}`);
    }

    return NextResponse.json({ success: true });
  } catch (err: any) {
    console.error('[summary-apps POST] Error:', err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const body = await request.json();
    const { appId } = body;

    if (!appId) {
      return NextResponse.json({ error: 'App ID is required' }, { status: 400 });
    }

    const baseUrl = process.env.NEXT_PUBLIC_OMI_API_URL;
    const secret = process.env.OMI_API_SECRET_KEY;
    if (!baseUrl || !secret) {
      throw new Error('OMI API env vars missing');
    }

    const res = await fetch(`${baseUrl}/v1/summary-app-ids/${appId}`, {
      method: 'DELETE',
      headers: {
        'secret-key': secret,
      },
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Failed to remove summary app: ${res.status} ${text}`);
    }

    return NextResponse.json({ success: true });
  } catch (err: any) {
    console.error('[summary-apps DELETE] Error:', err);
    return NextResponse.json({ error: err?.message || 'Internal Server Error' }, { status: 500 });
  }
}


