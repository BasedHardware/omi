import { NextRequest, NextResponse } from 'next/server';
import { verifyFirebaseToken } from '@/lib/firebase/admin';

/**
 * Verify that the request comes from an authenticated admin user.
 * Checks valid Firebase ID token in Authorization header.
 * The adminData collection check is done client-side by auth-provider.
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
    return { uid: decodedToken.uid };
  } catch (error) {
    console.error('Error verifying admin token:', error);
    return NextResponse.json({ error: 'Internal server error during auth' }, { status: 500 });
  }
}
