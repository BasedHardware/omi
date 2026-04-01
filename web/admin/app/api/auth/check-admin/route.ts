import { NextRequest, NextResponse } from 'next/server';
import { verifyFirebaseToken, getDb } from '@/lib/firebase/admin';

export async function GET(request: NextRequest) {
  const authorization = request.headers.get('Authorization');
  if (!authorization || !authorization.startsWith('Bearer ')) {
    return NextResponse.json({ isAdmin: false }, { status: 401 });
  }

  const token = authorization.split('Bearer ')[1];
  try {
    const decodedToken = await verifyFirebaseToken(token);
    if (!decodedToken) {
      return NextResponse.json({ isAdmin: false }, { status: 401 });
    }

    const db = getDb();
    const adminDoc = await db.collection('adminData').doc(decodedToken.uid).get();
    return NextResponse.json({ isAdmin: adminDoc.exists });
  } catch (error) {
    console.error('Error checking admin status:', error);
    return NextResponse.json({ isAdmin: false }, { status: 500 });
  }
}
