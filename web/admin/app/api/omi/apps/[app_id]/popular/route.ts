import { NextResponse } from 'next/server';
import { verifyFirebaseToken } from '@/lib/firebase/admin';
import omiApiClient from '@/lib/services/omi-api/client';

export const dynamic = 'force-dynamic';

export async function PATCH(
  request: Request,
  { params }: { params: { app_id: string } }
) {
  const { app_id } = params;
  if (!app_id) {
    return NextResponse.json({ error: 'App ID is required' }, { status: 400 });
  }

  // 1. Verify Firebase Token
  const authorization = request.headers.get('Authorization');
  if (!authorization?.startsWith('Bearer ')) {
    return NextResponse.json({ error: 'Unauthorized: Missing Bearer token' }, { status: 401 });
  }
  const idToken = authorization.split('Bearer ')[1];

  let userUid: string;
  try {
    const decodedToken = await verifyFirebaseToken(idToken);
    if (!decodedToken) {
        return NextResponse.json({ error: 'Unauthorized: Invalid token' }, { status: 401 });
    }
    userUid = decodedToken.uid;
  } catch (error) {
    console.error('Firebase Auth Error during verification:', error);
    return NextResponse.json({ error: 'Unauthorized: Error verifying token' }, { status: 401 });
  }

  // 2. Parse request body to get the value
  let requestBody;
  try {
    requestBody = await request.json();
  } catch (error) {
    return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
  }

  const { value } = requestBody;
  if (typeof value !== 'boolean') {
    return NextResponse.json({ error: 'Value must be a boolean' }, { status: 400 });
  }

  // 3. Call the Omi API to mark app as popular
  try {
    const endpoint = `/v1/apps/${app_id}/popular?value=${value}`;
    const result = await omiApiClient(endpoint, userUid, {
      method: 'PATCH',
    });

    return NextResponse.json({ success: true, data: result });

  } catch (error: any) {
    console.error(`API Error marking app ${app_id} as popular:`, error);
    
    // Handle specific API errors
    if (error.status) {
      return NextResponse.json({ 
        error: error.message || 'Failed to mark app as popular',
        details: error.details 
      }, { status: error.status });
    }
    
    return NextResponse.json({ 
      error: 'Internal Server Error' 
    }, { status: 500 });
  }
}
