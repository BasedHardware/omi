import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import omiApiClient from '@/lib/services/omi-api/client';

export const dynamic = 'force-dynamic';

export async function PATCH(
  request: NextRequest,
  { params }: { params: { app_id: string } }
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { app_id } = params;
  if (!app_id) {
    return NextResponse.json({ error: 'App ID is required' }, { status: 400 });
  }

  // Parse request body to get the value
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
    const result = await omiApiClient(endpoint, authResult.uid, {
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
