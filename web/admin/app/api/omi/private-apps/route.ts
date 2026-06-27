import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getDb } from '@/lib/firebase/admin';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const db = getDb();
    const snapshot = await db
      .collection('plugins_data')
      .where('private', '==', true)
      .where('deleted', '!=', true)
      .get();

    const apps = snapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    }));

    return NextResponse.json({ apps });
  } catch (error) {
    console.error('Error fetching private apps:', error);
    return NextResponse.json(
      { error: 'Failed to fetch private apps' },
      { status: 500 }
    );
  }
}
