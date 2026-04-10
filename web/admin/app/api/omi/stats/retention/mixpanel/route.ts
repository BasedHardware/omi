import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { transformRetention } from './transform';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const secret = process.env.MIXPANEL_SECRET;
    const apiBase = process.env.MIXPANEL_API_BASE || 'https://mixpanel.com/api/2.0';

    if (!secret) {
      return NextResponse.json({ data: [], cohorts: [], totalCohorts: 0, totalUsers: 0, unavailable: true });
    }

    const searchParams = request.nextUrl.searchParams;
    const days = parseInt(searchParams.get('days') || '30', 10);
    const platform = searchParams.get('platform') || '';

    const toDate = new Date();
    const fromDate = new Date();
    fromDate.setDate(fromDate.getDate() - days);

    const formatDate = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

    const params = new URLSearchParams({
      from_date: formatDate(fromDate),
      to_date: formatDate(toDate),
      retention_type: 'birth',
      born_event: '$ae_session',
      event: '$ae_session',
      unit: 'day',
      interval_count: String(days),
    });

    if (platform === 'macos') {
      // Use born_where to define the cohort as "users whose first session was on macOS".
      // This makes cohort.first = macOS-born users, so retention never exceeds 100%.
      // Using `where` instead would filter events per-day independently, allowing
      // counts[N] > counts[0] and producing >100% retention.
      params.set('born_where', 'properties["$os"]=="macOS"');
    }

    const url = `${apiBase.replace(/\/$/, '')}/retention?${params.toString()}`;
    const auth = Buffer.from(`${secret}:`).toString('base64');

    const response = await fetch(url, {
      headers: {
        Authorization: `Basic ${auth}`,
        Accept: 'application/json',
      },
    });

    if (!response.ok) {
      const text = await response.text();
      console.error('Mixpanel retention API error:', response.status, text);
      return NextResponse.json(
        { error: `Mixpanel API error: ${response.status}` },
        { status: 502 }
      );
    }

    const raw = await response.json();

    // Check for API-level errors
    if (raw.error) {
      console.error('Mixpanel retention error:', raw.error);
      return NextResponse.json(
        { error: `Mixpanel error: ${raw.error}` },
        { status: 502 }
      );
    }

    const result = transformRetention(raw);
    return NextResponse.json(result);
  } catch (error) {
    console.error('Error fetching Mixpanel retention:', error);
    return NextResponse.json(
      { error: 'Failed to fetch Mixpanel retention data' },
      { status: 500 }
    );
  }
}
