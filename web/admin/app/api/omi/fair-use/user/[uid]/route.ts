import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getDb } from '@/lib/firebase/admin';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest, { params }: { params: Promise<{ uid: string }> }) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { uid } = await params;

  try {
    const db = getDb();

    // Fetch state
    const stateDoc = await db.collection('users').doc(uid).collection('fair_use_state').doc('current').get();
    const state = stateDoc.exists ? stateDoc.data() : {};

    // Fetch events (newest first, limit 50)
    const eventsSnapshot = await db
      .collection('users')
      .doc(uid)
      .collection('fair_use_events')
      .orderBy('created_at', 'desc')
      .limit(50)
      .get();

    const events = eventsSnapshot.docs.map((doc) => {
      const data = doc.data();
      return {
        ...data,
        id: doc.id,
        created_at: data.created_at?.toDate?.()?.toISOString() || data.created_at,
        resolved_at: data.resolved_at?.toDate?.()?.toISOString() || data.resolved_at,
      };
    });

    // Fetch basic user profile
    const userDoc = await db.collection('users').doc(uid).get();
    const userData = userDoc.exists ? userDoc.data() : {};
    const profile = {
      email: userData?.email || '',
      name: userData?.name || '',
      subscription_plan: userData?.subscription?.plan || 'basic',
    };

    // Serialize timestamps in state
    const serializedState: Record<string, unknown> = {};
    if (state) {
      for (const [key, value] of Object.entries(state)) {
        if (value && typeof value === 'object' && 'toDate' in value) {
          serializedState[key] = (value as { toDate: () => Date }).toDate().toISOString();
        } else {
          serializedState[key] = value;
        }
      }
    }

    return NextResponse.json({ uid, state: serializedState, events, profile });
  } catch (error) {
    console.error('Error fetching user fair use detail:', error);
    return NextResponse.json({ error: 'Failed to fetch user detail' }, { status: 500 });
  }
}
