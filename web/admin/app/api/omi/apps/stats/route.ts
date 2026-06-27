import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getApps, getUnapprovedApps } from '@/lib/services/omi-api/apps';
import { OmiApiError } from '@/lib/services/omi-api/client';

export const dynamic = 'force-dynamic';

function withCors(response: NextResponse) {
  const headers = response.headers;
  headers.set('Access-Control-Allow-Origin', '*');
  headers.set('Access-Control-Allow-Methods', 'GET,OPTIONS');
  headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  headers.set('Vary', 'Origin');
  return response;
}

export async function OPTIONS() {
  return withCors(new NextResponse(null, { status: 204 }));
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return withCors(authResult);

  try {
    // Fetch both regular apps and unapproved apps — use allSettled
    // so one failure doesn't crash the entire stats endpoint
    const results = await Promise.allSettled([
      getApps(authResult.uid),
      getUnapprovedApps(authResult.uid)
    ]);

    const apps = results[0].status === 'fulfilled' ? results[0].value : [];
    const unapprovedApps = results[1].status === 'fulfilled' ? results[1].value : [];

    if (results[0].status === 'rejected') {
      console.error('[API Route] Error fetching apps:', results[0].reason);
    }
    if (results[1].status === 'rejected') {
      console.error('[API Route] Error fetching unapproved apps:', results[1].reason);
    }

    if (results.every((r) => r.status === 'rejected')) {
      return withCors(NextResponse.json(
        { error: 'All app data sources failed' },
        { status: 502 }
      ));
    }

    // Filter out persona apps from regular apps
    const filteredApps = apps.filter(app =>
      !app.capabilities?.includes('persona')
    );

    // Calculate stats (excluding persona apps)
    let approvedCount = 0;
    let paidCount = 0;

    filteredApps.forEach((app) => {
      // Only count as approved if explicitly approved
      if (app.approved === true) {
        approvedCount++;
      }
      if (app.is_paid) {
        paidCount++;
      }
    });

    // Filter unapproved apps to match review page logic:
    // 1. Only public apps (already handled by getUnapprovedApps)
    // 2. Only apps that are actually pending review (not rejected)
    // 3. Exclude persona apps
    const filteredUnapprovedApps = unapprovedApps.filter(app =>
      (app.status === 'pending' || app.status === 'under-review') &&
      !app.capabilities?.includes('persona')
    );

    const partial = results.some((r) => r.status === 'rejected');
    const stats = {
      total: filteredApps.length,
      approved: approvedCount,
      inReview: filteredUnapprovedApps.length, // Only public apps awaiting review
      paid: paidCount,
      partial,
    };

    return withCors(NextResponse.json(stats));

  } catch (error) {
    console.error('[API Route] Error fetching app stats:', error);
    if (error instanceof OmiApiError) {
      return withCors(
        NextResponse.json({ error: error.message, details: error.details }, { status: error.status })
      );
    }
    return withCors(NextResponse.json({ error: 'Internal Server Error' }, { status: 500 }));
  }
}
