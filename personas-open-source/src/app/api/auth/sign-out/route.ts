import { NextResponse } from 'next/server';
import { auth } from '@/lib/firebase-admin';
import { cookies } from 'next/headers';

export async function POST() {
  try {
    const cookieStore = await cookies();
    const sessionCookie = cookieStore.get('session')?.value;
    
    // If session cookie exists
    if (sessionCookie) {
      // Verify and get user info
      try {
        const decodedClaims = await auth.verifySessionCookie(sessionCookie);
        // Revoke all user sessions
        await auth.revokeRefreshTokens(decodedClaims.uid);
      } catch (error) {
        console.log('Invalid session cookie or already revoked');
        // Continue to delete the cookie even if verification fails
      }
    }
    
    // Clear the session cookie
    const response = NextResponse.json({ success: true });
    response.cookies.delete('session');
    return response;
  } catch (error: any) {
    console.error('Error signing out:', error);
    return NextResponse.json({ error: 'Failed to sign out' }, { status: 500 });
  }
}