import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getDb } from '@/lib/firebase/admin';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest, { params }: { params: Promise<{ caseRef: string }> }) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { caseRef } = await params;

  try {
    const db = getDb();
    const query = db.collectionGroup('fair_use_events').where('case_ref', '==', caseRef).limit(1);
    const snapshot = await query.get();

    if (snapshot.empty) {
      return NextResponse.json({ error: `Case ${caseRef} not found` }, { status: 404 });
    }

    const doc = snapshot.docs[0];
    const data = doc.data();
    const pathParts = doc.ref.path.split('/');
    const uid = pathParts.length >= 2 ? pathParts[1] : '';

    return NextResponse.json({
      ...data,
      uid,
      event_id: doc.id,
      created_at: data.created_at?.toDate?.()?.toISOString() || data.created_at,
      resolved_at: data.resolved_at?.toDate?.()?.toISOString() || data.resolved_at,
    });
  } catch (error) {
    console.error('Error looking up case:', error);
    return NextResponse.json({ error: 'Failed to look up case' }, { status: 500 });
  }
}
