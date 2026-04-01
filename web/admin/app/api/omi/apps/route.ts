import { NextResponse } from 'next/server';
import { verifyFirebaseToken } from '@/lib/firebase/admin'; // Import the verifier
import { getApps } from '@/lib/services/omi-api/apps'; // Import your Omi service
import { OmiApiError } from '@/lib/services/omi-api/client'; // Import custom error

// Force dynamic rendering for this route as it uses request headers
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
  const uid = decodedToken.uid;

  try {
    const apps = await getApps(uid);
    return NextResponse.json(apps);

  } catch (error) {
    console.error('[API Route] Error fetching Omi apps:', error);
    if (error instanceof OmiApiError) {
      // Forward the status and details from the Omi API error
      return NextResponse.json({ error: error.message, details: error.details }, { status: error.status });
    }
    // Generic server error
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

// You would add similar POST, PATCH, DELETE handlers here as needed,
// each verifying the token and calling the corresponding service function. 