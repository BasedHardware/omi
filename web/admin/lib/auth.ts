import { NextRequest, NextResponse } from 'next/server';
import { verifyFirebaseToken, getDb } from '@/lib/firebase/admin';

/**
 * Verify that the request comes from an authenticated admin user.
 * Checks: (1) valid Firebase ID token in Authorization header,
 * (2) user's UID exists in the adminData collection.
 * Returns the decoded token on success, or a NextResponse error on failure.
 */
export async function verifyAdmin(request: NextRequest): Promise<
  { uid: string } | NextResponse
> {
  const authorization = request.headers.get('Authorization');
  if (!authorization || !authorization.startsWith('Bearer ')) {
    return NextResponse.json({ error: 'Unauthorized: Missing or invalid token' }, { status: 401 });
  }

  const token = authorization.split('Bearer ')[1];
  try {
    const decodedToken = await verifyFirebaseToken(token);
    if (!decodedToken) {
      return NextResponse.json({ error: 'Unauthorized: Invalid token' }, { status: 401 });
    }

    const db = getDb();
    const adminDoc = await db.collection('adminData').doc(decodedToken.uid).get();
    if (!adminDoc.exists) {
      return NextResponse.json({ error: 'Forbidden: Not an admin' }, { status: 403 });
    }

    return { uid: decodedToken.uid };
  } catch (error) {
    console.error('Error verifying admin:', error);
    return NextResponse.json({ error: 'Internal server error during auth' }, { status: 500 });
  }
}
