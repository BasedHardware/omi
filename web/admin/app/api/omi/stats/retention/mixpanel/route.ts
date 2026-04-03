import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const secret = process.env.MIXPANEL_SECRET;
    const apiBase = process.env.MIXPANEL_API_BASE || 'https://mixpanel.com/api/2.0';

    if (!secret) {
      return NextResponse.json(
        { error: 'Mixpanel credentials not configured' },
        { status: 500 }
      );
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
      params.set('where', 'properties["$os"]=="macOS"');
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

    // raw format: { "YYYY-MM-DDTHH:MM:SS": { counts: [n0, n1, ...], first: N }, ... }
    // Filter out non-cohort keys like "request", "error"
    const cohortDates = Object.keys(raw)
      .filter((k) => typeof raw[k] === 'object' && raw[k] !== null && 'counts' in raw[k])
      .sort();
    if (cohortDates.length === 0) {
      return NextResponse.json({ data: [], totalCohorts: 0, totalUsers: 0 });
    }

    // Find max retention days across all cohorts
    let maxDays = 0;
    for (const date of cohortDates) {
      const counts = raw[date]?.counts;
      if (Array.isArray(counts) && counts.length > maxDays) {
        maxDays = counts.length;
      }
    }

    // Average retention across all cohorts for each day
    const data: { day: number; retention: number }[] = [];
    let totalUsers = 0;

    // Per-cohort retention curves
    const cohorts: { date: string; users: number; data: { day: number; retention: number }[] }[] = [];

    for (const date of cohortDates) {
      const cohort = raw[date];
      if (!cohort || !Array.isArray(cohort.counts)) continue;

      const first = cohort.counts[0] || 0;
      if (first === 0) continue;

      totalUsers += first;
      const label = date.split('T')[0]; // "YYYY-MM-DD"
      const curve: { day: number; retention: number }[] = [];

      for (let dayIdx = 0; dayIdx < cohort.counts.length; dayIdx++) {
        curve.push({
          day: dayIdx,
          retention: Math.round((cohort.counts[dayIdx] / first) * 100 * 100) / 100,
        });
      }

      cohorts.push({ date: label, users: first, data: curve });
    }

    for (let dayIdx = 0; dayIdx < maxDays; dayIdx++) {
      let sumPct = 0;
      let cohortCount = 0;

      for (const date of cohortDates) {
        const cohort = raw[date];
        if (!cohort || !Array.isArray(cohort.counts)) continue;

        // Use counts[0] as base when filtering, since `first` may be unfiltered
        const first = cohort.counts[0] || 0;
        if (first === 0) continue;
        if (dayIdx >= cohort.counts.length) continue;

        sumPct += (cohort.counts[dayIdx] / first) * 100;
        cohortCount++;
      }

      if (cohortCount > 0) {
        data.push({
          day: dayIdx,
          retention: Math.round((sumPct / cohortCount) * 100) / 100,
        });
      }
    }

    return NextResponse.json({
      data,
      cohorts,
      totalCohorts: cohortDates.length,
      totalUsers,
    });
  } catch (error) {
    console.error('Error fetching Mixpanel retention:', error);
    return NextResponse.json(
      { error: 'Failed to fetch Mixpanel retention data' },
      { status: 500 }
    );
  }
}
