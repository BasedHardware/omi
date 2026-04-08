import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getDb } from '@/lib/firebase/admin';

export const dynamic = 'force-dynamic';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ uid: string; eventId: string }> }
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { uid, eventId } = await params;
  const adminUid = authResult.uid;

  const { searchParams } = new URL(request.url);
  const notes = searchParams.get('notes') || '';

  try {
    const db = getDb();
    const ref = db.collection('users').doc(uid).collection('fair_use_events').doc(eventId);

    const doc = await ref.get();
    if (!doc.exists) {
      return NextResponse.json({ error: 'Event not found' }, { status: 404 });
    }

    await ref.update({
      resolved: true,
      resolved_at: new Date(),
      resolved_by: adminUid,
      admin_notes: notes,
    });

    return NextResponse.json({ status: 'resolved' });
  } catch (error) {
    console.error('Error resolving fair use event:', error);
    return NextResponse.json({ error: 'Failed to resolve event' }, { status: 500 });
  }
}
