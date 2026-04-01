import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
// Assume a function exists to get unapproved apps from the Omi API
// You might need to create this in lib/services/omi-api/apps.ts
import { getUnapprovedApps } from '@/lib/services/omi-api/apps';
import { OmiApiError } from '@/lib/services/omi-api/client';

// Force dynamic rendering for this route as it needs auth
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const apps = await getUnapprovedApps(authResult.uid);
    return NextResponse.json(apps); 

  } catch (error) {
    console.error('[API Route] Error fetching Omi unapproved apps:', error);
    if (error instanceof OmiApiError) {
      return NextResponse.json({ error: error.message, details: error.details }, { status: error.status });
    }
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
} 