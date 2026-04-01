import { NextResponse } from 'next/server';
import { verifyFirebaseToken, getDb } from '@/lib/firebase/admin';

export const dynamic = 'force-dynamic';

export async function GET(
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

  try {
    const decodedToken = await verifyFirebaseToken(idToken);
    if (!decodedToken) {
        return NextResponse.json({ error: 'Unauthorized: Invalid token' }, { status: 401 });
    }
    // userUid = decodedToken.uid; // User UID available if needed for further checks
  } catch (error) {
    console.error('Firebase Auth Error during verification:', error);
    return NextResponse.json({ error: 'Unauthorized: Error verifying token' }, { status: 401 });
  }

  // 2. Fetch App Details from Firestore
  try {
    const db = getDb();
    const appDocRef = db.collection('plugins_data').doc(app_id);
    const appDoc = await appDocRef.get();

    if (!appDoc.exists) {
      return NextResponse.json({ error: 'App details not found' }, { status: 404 });
    }

    const appDetails = appDoc.data();
    // Potentially transform or select specific fields if needed
    return NextResponse.json(appDetails, { status: 200 });

  } catch (error: any) {
    console.error(`Error fetching app details for ${app_id}:`, error);
    return NextResponse.json({ error: error.message || 'An internal server error occurred while fetching app details.' }, { status: 500 });
  }
} 