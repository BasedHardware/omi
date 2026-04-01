import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getDb } from '@/lib/firebase/admin';
import { invalidateEnforcementCache } from '@/lib/redis';

export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest, { params }: { params: Promise<{ uid: string }> }) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { uid } = await params;
  const adminUid = authResult.uid;

  try {
    const db = getDb();
    const ref = db.collection('users').doc(uid).collection('fair_use_state').doc('current');

    await ref.set(
      {
        stage: 'none',
        violation_count_7d: 0,
        violation_count_30d: 0,
        last_violation_at: null,
        throttle_until: null,
        restrict_until: null,
        last_classifier_score: 0.0,
        last_classifier_type: 'none',
        reset_by: adminUid,
        reset_at: new Date(),
        updated_at: new Date(),
      },
      { merge: true }
    );

    await invalidateEnforcementCache(uid);

    return NextResponse.json({ status: 'reset' });
  } catch (error) {
    console.error('Error resetting fair use state:', error);
    return NextResponse.json({ error: 'Failed to reset state' }, { status: 500 });
  }
}
