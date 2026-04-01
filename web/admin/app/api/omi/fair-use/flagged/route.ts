import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getDb } from '@/lib/firebase/admin';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { searchParams } = new URL(request.url);
  const stage = searchParams.get('stage');
  const parsedLimit = parseInt(searchParams.get('limit') || '50', 10);
  const limit = Math.min(Number.isNaN(parsedLimit) ? 50 : parsedLimit, 200);

  try {
    const db = getDb();
    let query = db.collectionGroup('fair_use_state') as FirebaseFirestore.Query;

    if (stage) {
      query = query.where('stage', '==', stage);
    } else {
      query = query.where('stage', 'in', ['warning', 'throttle', 'restrict']);
    }

    query = query.orderBy('updated_at', 'desc').limit(limit);

    const snapshot = await query.get();
    const users = snapshot.docs.map((doc) => {
      const data = doc.data();
      const pathParts = doc.ref.path.split('/');
      return {
        ...data,
        uid: pathParts.length >= 2 ? pathParts[1] : '',
        id: doc.id,
        updated_at: data.updated_at?.toDate?.()?.toISOString() || data.updated_at,
        created_at: data.created_at?.toDate?.()?.toISOString() || data.created_at,
        throttle_until: data.throttle_until?.toDate?.()?.toISOString() || data.throttle_until,
        restrict_until: data.restrict_until?.toDate?.()?.toISOString() || data.restrict_until,
        last_violation_at: data.last_violation_at?.toDate?.()?.toISOString() || data.last_violation_at,
        reset_at: data.reset_at?.toDate?.()?.toISOString() || data.reset_at,
      };
    });

    return NextResponse.json({ users });
  } catch (error) {
    console.error('Error fetching flagged users:', error);
    return NextResponse.json({ error: 'Failed to fetch flagged users' }, { status: 500 });
  }
}
