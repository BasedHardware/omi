import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getDb } from '@/lib/firebase/admin';
import { invalidateEnforcementCache } from '@/lib/redis';

export const dynamic = 'force-dynamic';

const VALID_STAGES = ['none', 'warning', 'throttle', 'restrict'] as const;

export async function POST(request: NextRequest, { params }: { params: Promise<{ uid: string }> }) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { uid } = await params;
  const { searchParams } = new URL(request.url);
  const stage = searchParams.get('stage');

  if (!stage || !(VALID_STAGES as readonly string[]).includes(stage)) {
    return NextResponse.json(
      { error: `Invalid stage. Must be one of: ${VALID_STAGES.join(', ')}` },
      { status: 400 }
    );
  }

  try {
    const db = getDb();
    const ref = db.collection('users').doc(uid).collection('fair_use_state').doc('current');

    const updates: Record<string, unknown> = {
      stage,
      updated_at: new Date(),
    };

    if (stage === 'none') {
      updates.throttle_until = null;
      updates.restrict_until = null;
    }

    await ref.set(updates, { merge: true });
    await invalidateEnforcementCache(uid);

    return NextResponse.json({ status: 'updated', stage });
  } catch (error) {
    console.error('Error setting fair use stage:', error);
    return NextResponse.json({ error: 'Failed to set stage' }, { status: 500 });
  }
}
