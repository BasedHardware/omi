import { NextResponse } from 'next/server';
import { verifyFirebaseToken } from '@/lib/firebase/admin';
// Assume a function exists to get unapproved apps from the Omi API
// You might need to create this in lib/services/omi-api/apps.ts
import { getUnapprovedApps } from '@/lib/services/omi-api/apps'; 
import { OmiApiError } from '@/lib/services/omi-api/client';

// Force dynamic rendering for this route as it needs auth
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  // 1. Get token from Authorization header
  const authorization = request.headers.get('Authorization');
  if (!authorization || !authorization.startsWith('Bearer ')) {
    return NextResponse.json({ error: 'Unauthorized: Missing or invalid token' }, { status: 401 });
  }
  const token = authorization.split('Bearer ')[1];

  // 2. Verify the token using Firebase Admin SDK
  const decodedToken = await verifyFirebaseToken(token);
  if (!decodedToken) {
    return NextResponse.json({ error: 'Unauthorized: Invalid token' }, { status: 401 });
  }
  // We might not strictly need the UID for public unapproved, but verification is good practice
  // const uid = decodedToken.uid;

  // 3. Optional Admin Check (already done client-side, but good for API security)
  // const isAdmin = await checkAdminStatus(uid); 
  // if (!isAdmin) { 
  //   return NextResponse.json({ error: 'Forbidden: User is not an admin' }, { status: 403 });
  // }

  // 4. Call the Omi API service function for unapproved apps
  try {
    const apps = await getUnapprovedApps(decodedToken.uid); // Call the specific service function
    return NextResponse.json(apps); 

  } catch (error) {
    console.error('[API Route] Error fetching Omi unapproved apps:', error);
    if (error instanceof OmiApiError) {
      return NextResponse.json({ error: error.message, details: error.details }, { status: error.status });
    }
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
} 