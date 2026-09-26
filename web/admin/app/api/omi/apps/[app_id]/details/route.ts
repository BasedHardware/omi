import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/firebase/admin';
import { verifyAdmin } from '@/lib/auth';
import { isSafeDocumentId } from '@/lib/firestore-doc-id.mjs';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest, props: { params: Promise<{ app_id: string }> }) {
  const params = await props.params;
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const app_id = params.app_id;
  if (!app_id || !isSafeDocumentId(app_id)) {
    return NextResponse.json({ error: 'App ID is required' }, { status: 400 });
  }

  // Fetch App Details from Firestore
  try {
    const db = getDb();
    const appDocRef = db.collection('plugins_data').doc(app_id);
    const appDoc = await appDocRef.get();

    if (!appDoc.exists) {
      return NextResponse.json({ error: 'App details not found' }, { status: 404 });
    }

    const appDetails = appDoc.data();
    // Potentially transform or select specific fields if needed
    return NextResponse.json(appDetails, { status: 200 });

  } catch (error: any) {
    console.error(`Error fetching app details for ${app_id}:`, error);
    return NextResponse.json({ error: error.message || 'An internal server error occurred while fetching app details.' }, { status: 500 });
  }
} 