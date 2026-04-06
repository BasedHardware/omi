import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { reviewApp } from '@/lib/services/omi-api/apps';

export const dynamic = 'force-dynamic'; // Necessary because we read headers

interface ReviewRequestBody {
  action: 'approve' | 'reject';
  reason?: string; // Optional for rejection
}

export async function POST(
  request: NextRequest,
  { params }: { params: { app_id: string } }
) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { app_id } = params;
  if (!app_id) {
    return NextResponse.json({ error: 'App ID is required' }, { status: 400 });
  }

  // Parse Request Body
  let requestBody: ReviewRequestBody;
  try {
    requestBody = await request.json();
  } catch (error) {
    return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
  }

  const { action, reason } = requestBody;

  if (!action || (action !== 'approve' && action !== 'reject')) {
    return NextResponse.json({ error: 'Invalid action specified. Use "approve" or "reject".' }, { status: 400 });
  }

  if (action === 'reject' && !reason) {
    // Consider if reason should be mandatory for rejection
    // return NextResponse.json({ error: 'Reason is required for rejection.' }, { status: 400 });
  }

  // 3. Call Omi API Service
  try {
    const result = await reviewApp(authResult.uid, app_id, action, reason);

    if (result.success) {
      return NextResponse.json({ message: `App ${action}d successfully.` }, { status: 200 });
    } else {
      return NextResponse.json({ error: result.message || `Failed to ${action} app.` }, { status: 500 });
    }
  } catch (error: any) {
    console.error(`API Review Error (${action}ing app ${app_id}):`, error);
    return NextResponse.json({ error: error.message || 'An internal server error occurred while reviewing the app.' }, { status: 500 });
  }
} 