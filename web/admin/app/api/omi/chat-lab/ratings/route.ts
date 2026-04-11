import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getDb } from '@/lib/firebase/admin';

export const dynamic = 'force-dynamic';

function getISOWeek(date: Date): string {
  const d = new Date(date);
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const { searchParams } = new URL(request.url);
  const platform = searchParams.get('platform') || 'all';
  const groupBy = searchParams.get('group_by') || 'week'; // 'week' or 'version'

  try {
    const db = getDb();

    const snapshot = await db
      .collection('analytics')
      .where('type', '==', 'chat_message')
      .limit(10000)
      .get();

    if (groupBy === 'version') {
      // Group by app_version
      const versionStats = new Map<string, { thumbs_up: number; thumbs_down: number }>();

      for (const doc of snapshot.docs) {
        const data = doc.data();
        const value = data.value;
        if (value !== 1 && value !== -1) continue;
        if (platform !== 'all') {
          if (platform === 'desktop' && data.platform !== 'desktop') continue;
          if (platform === 'mobile' && data.platform !== 'mobile') continue;
        }

        const version = data.app_version || 'unknown';
        const entry = versionStats.get(version) || { thumbs_up: 0, thumbs_down: 0 };
        if (value === 1) entry.thumbs_up++;
        else entry.thumbs_down++;
        versionStats.set(version, entry);
      }

      const versions = Array.from(versionStats.entries())
        .map(([version, stats]) => ({
          version,
          thumbs_up: stats.thumbs_up,
          thumbs_down: stats.thumbs_down,
        }))
        .sort((a, b) => a.version.localeCompare(b.version, undefined, { numeric: true }));

      const total_up = versions.reduce((s, v) => s + v.thumbs_up, 0);
      const total_down = versions.reduce((s, v) => s + v.thumbs_down, 0);

      return NextResponse.json({ versions, total_up, total_down, platform, group_by: 'version' });
    }

    // Default: group by week
    const weeklyStats = new Map<string, { thumbs_up: number; thumbs_down: number }>();

    for (const doc of snapshot.docs) {
      const data = doc.data();
      const value = data.value;
      if (value !== 1 && value !== -1) continue;
      if (platform !== 'all') {
        if (platform === 'desktop' && data.platform !== 'desktop') continue;
        if (platform === 'mobile' && data.platform !== 'mobile') continue;
      }

      const createdAt = data.created_at;
      if (!createdAt) continue;
      const date = typeof createdAt === 'string'
        ? new Date(createdAt)
        : createdAt.toDate?.() ?? new Date(createdAt);

      const week = getISOWeek(date);
      const entry = weeklyStats.get(week) || { thumbs_up: 0, thumbs_down: 0 };
      if (value === 1) entry.thumbs_up++;
      else entry.thumbs_down++;
      weeklyStats.set(week, entry);
    }

    const result = Array.from(weeklyStats.entries())
      .map(([week, stats]) => ({
        week,
        thumbs_up: stats.thumbs_up,
        thumbs_down: stats.thumbs_down,
      }))
      .sort((a, b) => a.week.localeCompare(b.week));

    const total_up = result.reduce((sum, w) => sum + w.thumbs_up, 0);
    const total_down = result.reduce((sum, w) => sum + w.thumbs_down, 0);

    return NextResponse.json({ weeks: result, total_up, total_down, platform, group_by: 'week' });
  } catch (error) {
    console.error('[Chat Lab] Error fetching ratings:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
