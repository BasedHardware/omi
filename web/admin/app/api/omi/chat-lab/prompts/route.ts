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
      .collection('admin')
      .doc('chat_lab')
      .collection('versions')
      .orderBy('created_at', 'desc')
      .get();

    const versions = snapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    }));

    return NextResponse.json({ versions });
  } catch (error) {
    console.error('[Chat Lab] Error fetching prompt versions:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const body = await request.json();
    const { name, prompt_text, floating_prefix, notes } = body;

    if (!name || !prompt_text) {
      return NextResponse.json({ error: 'name and prompt_text are required' }, { status: 400 });
    }

    const db = getDb();
    const docRef = await db
      .collection('admin')
      .doc('chat_lab')
      .collection('versions')
      .add({
        name,
        prompt_text,
        floating_prefix: floating_prefix || '',
        notes: notes || '',
        created_at: new Date().toISOString(),
        created_by: authResult.uid,
      });

    return NextResponse.json({ id: docRef.id }, { status: 201 });
  } catch (error) {
    console.error('[Chat Lab] Error creating prompt version:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
