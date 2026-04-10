import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/firebase/admin';
import { verifyAdmin } from '@/lib/auth';

export const dynamic = 'force-dynamic';

const MENTOR_APP_ID = 'mentor';
const MARKETPLACE_MENTOR_APP_ID = 'omi-your-mentor-and-teacher-01JCPRSZ7FS40FHFNSJZEWR8R1';

type FloatingBarCtrPoint = {
  date: string;
  sent: number;
  clicked: number;
  dismissed: number;
  ctr: number;
};

type FloatingBarCtrStats = {
  dailyData: FloatingBarCtrPoint[];
  summary: {
    sent: number;
    clicked: number;
    dismissed: number;
    ctr: number;
    uniqueClickers: number;
    mode: 'surface_tagged' | 'all_notifications_fallback';
  };
};

async function queryPostHog(host: string, projectId: string, apiKey: string, query: string) {
  const response = await fetch(`${host}/api/projects/${projectId}/query/`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query: { kind: 'HogQLQuery', query } }),
    signal: AbortSignal.timeout(15000),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`PostHog API error ${response.status}: ${text}`);
  }

  return response.json();
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const db = getDb();
    const searchParams = request.nextUrl.searchParams;
    const days = parseInt(searchParams.get('days') || '30', 10);
    const posthogHost = (process.env.POSTHOG_HOST || 'https://us.posthog.com').replace(/\/$/, '');
    const posthogApiKey = process.env.POSTHOG_PERSONAL_API_KEY;
    const posthogProjectId = process.env.POSTHOG_PROJECT_ID;

    const endDate = new Date();
    const startDate = new Date();
    startDate.setUTCDate(startDate.getUTCDate() - days);
    startDate.setUTCHours(0, 0, 0, 0);

    // Initialize day buckets (all dates in UTC)
    const dayBuckets: Record<string, {
      mentorSent: number;
      marketplaceMentorSent: number;
      uniqueUsersMentor: Set<string>;
      uniqueUsersMarketplace: Set<string>;
    }> = {};
    const dateKeys: string[] = [];
    const current = new Date(startDate);
    while (current <= endDate) {
      const key = current.toISOString().split('T')[0];
      dateKeys.push(key);
      dayBuckets[key] = {
        mentorSent: 0,
        marketplaceMentorSent: 0,
        uniqueUsersMentor: new Set(),
        uniqueUsersMarketplace: new Set(),
      };
      current.setUTCDate(current.getUTCDate() + 1);
    }

    // Hourly timeline: each hour in the range gets its own bucket
    const hourlyTimeline: Record<string, { mentor: number; marketplace: number }> = {};
    // Build all hour keys for the last 168 hours (7 days)
    const hourlyKeys: string[] = [];
    const hourStart = new Date();
    hourStart.setUTCHours(hourStart.getUTCHours() - 167, 0, 0, 0);
    const hourCurrent = new Date(hourStart);
    while (hourCurrent <= endDate) {
      const hk = hourCurrent.toISOString().slice(0, 13); // "2026-02-19T14"
      hourlyKeys.push(hk);
      hourlyTimeline[hk] = { mentor: 0, marketplace: 0 };
      hourCurrent.setUTCHours(hourCurrent.getUTCHours() + 1);
    }

    const startMs = startDate.getTime();
    const endMs = endDate.getTime();
    const usersRef = db.collection('users');
    let floatingBarCtr: FloatingBarCtrStats | null = null;

    const fetchNotifications = async () => {
      // Try collection group first
      try {
        const [mentorSnap, marketplaceSnap] = await Promise.all([
          db.collectionGroup('messages')
            .where('app_id', '==', MENTOR_APP_ID)
            .where('created_at', '>=', startDate)
            .where('created_at', '<=', endDate)
            .get(),
          db.collectionGroup('messages')
            .where('app_id', '==', MARKETPLACE_MENTOR_APP_ID)
            .where('created_at', '>=', startDate)
            .where('created_at', '<=', endDate)
            .get(),
        ]);
        for (const doc of mentorSnap.docs) {
          const data = doc.data();
          const createdAt = data.created_at?.toDate?.() ?? new Date(data.created_at);
          const ts = createdAt.getTime();
          if (ts < startMs || ts > endMs) continue;
          const dayKey = createdAt.toISOString().split('T')[0];
          const uid = doc.ref.parent.parent?.id || 'unknown';
          if (dayBuckets[dayKey]) { dayBuckets[dayKey].mentorSent++; dayBuckets[dayKey].uniqueUsersMentor.add(uid); }
          const hk = createdAt.toISOString().slice(0, 13);
          if (hourlyTimeline[hk]) hourlyTimeline[hk].mentor++;
        }
        for (const doc of marketplaceSnap.docs) {
          const data = doc.data();
          const createdAt = data.created_at?.toDate?.() ?? new Date(data.created_at);
          const ts = createdAt.getTime();
          if (ts < startMs || ts > endMs) continue;
          const dayKey = createdAt.toISOString().split('T')[0];
          const uid = doc.ref.parent.parent?.id || 'unknown';
          if (dayBuckets[dayKey]) { dayBuckets[dayKey].marketplaceMentorSent++; dayBuckets[dayKey].uniqueUsersMarketplace.add(uid); }
          const hk = createdAt.toISOString().slice(0, 13);
          if (hourlyTimeline[hk]) hourlyTimeline[hk].marketplace++;
        }
        return;
      } catch {
        // Collection group needs index — fall back to per-user queries
      }

      // Fallback: query all mentor-enabled users
      const enabledUsersSnap = await usersRef
        .where('mentor_notification_frequency', '>', 0)
        .select()
        .limit(5000)
        .get();

      const enabledUserIds = enabledUsersSnap.docs.map(doc => doc.id);

      // Fire ALL queries at once — only ~400 users × 2 = ~800 queries
      const allPromises = enabledUserIds.flatMap(uid => [
        db.collection('users').doc(uid).collection('messages')
          .where('app_id', '==', MENTOR_APP_ID)
          .get()
          .then(snap => ({ uid, type: 'mentor' as const, docs: snap.docs }))
          .catch(() => ({ uid, type: 'mentor' as const, docs: [] as FirebaseFirestore.QueryDocumentSnapshot[] })),
        db.collection('users').doc(uid).collection('messages')
          .where('app_id', '==', MARKETPLACE_MENTOR_APP_ID)
          .get()
          .then(snap => ({ uid, type: 'marketplace' as const, docs: snap.docs }))
          .catch(() => ({ uid, type: 'marketplace' as const, docs: [] as FirebaseFirestore.QueryDocumentSnapshot[] })),
      ]);

      const results = await Promise.all(allPromises);
      for (const result of results) {
        for (const doc of result.docs) {
          const data = doc.data();
          const createdAt = data.created_at?.toDate?.() ?? new Date(data.created_at);
          const ts = createdAt.getTime();
          if (ts < startMs || ts > endMs) continue;
          const dayKey = createdAt.toISOString().split('T')[0];
          if (dayBuckets[dayKey]) {
            const hk = createdAt.toISOString().slice(0, 13);
            if (result.type === 'mentor') {
              dayBuckets[dayKey].mentorSent++;
              dayBuckets[dayKey].uniqueUsersMentor.add(result.uid);
              if (hourlyTimeline[hk]) hourlyTimeline[hk].mentor++;
            } else {
              dayBuckets[dayKey].marketplaceMentorSent++;
              dayBuckets[dayKey].uniqueUsersMarketplace.add(result.uid);
              if (hourlyTimeline[hk]) hourlyTimeline[hk].marketplace++;
            }
          }
        }
      }
    };

    const countsPromise = Promise.all([
      usersRef.where('notifications_enabled', '==', false).count().get(),
      usersRef.count().get(),
    ]);

    const fetchFloatingBarCtr = async () => {
      if (!posthogApiKey || !posthogProjectId) return null;

      const buildCtr = (
        dailyRows: [string, number, number, number][],
        summaryRow: [number, number, number, number] | undefined,
        mode: 'surface_tagged' | 'all_notifications_fallback'
      ) => {
        const ctrByDate = new Map(
          dailyRows.map(([date, sent, clicked, dismissed]) => {
            const normalizedDate = date.slice(0, 10);
            return [normalizedDate, { sent, clicked, dismissed }];
          })
        );

        const dailyData = dateKeys.map((date) => {
          const row = ctrByDate.get(date) ?? { sent: 0, clicked: 0, dismissed: 0 };
          return {
            date,
            sent: row.sent,
            clicked: row.clicked,
            dismissed: row.dismissed,
            ctr: row.sent > 0 ? Math.round((row.clicked / row.sent) * 1000) / 10 : 0,
          };
        });

        const [sent = 0, clicked = 0, dismissed = 0, uniqueClickers = 0] = summaryRow ?? [];
        return {
          dailyData,
          summary: {
            sent,
            clicked,
            dismissed,
            ctr: sent > 0 ? Math.round((clicked / sent) * 1000) / 10 : 0,
            uniqueClickers,
            mode,
          },
        };
      };

      const surfaceDailyCtrQuery = `
        SELECT
          toDate(timestamp) as day,
          countIf(event = 'Notification Sent') as sent,
          countIf(event = 'Notification Clicked') as clicked,
          countIf(event = 'Notification Dismissed') as dismissed
        FROM events
        WHERE event IN ('Notification Sent', 'Notification Clicked', 'Notification Dismissed')
          AND properties.$os_name = 'macOS'
          AND properties.notification_surface = 'floating_bar'
          AND timestamp >= now() - interval ${days} day
        GROUP BY day
        ORDER BY day
      `;

      const surfaceSummaryQuery = `
        SELECT
          countIf(event = 'Notification Sent') as sent,
          countIf(event = 'Notification Clicked') as clicked,
          countIf(event = 'Notification Dismissed') as dismissed,
          count(DISTINCT if(event = 'Notification Clicked', distinct_id, null)) as unique_clickers
        FROM events
        WHERE event IN ('Notification Sent', 'Notification Clicked', 'Notification Dismissed')
          AND properties.$os_name = 'macOS'
          AND properties.notification_surface = 'floating_bar'
          AND timestamp >= now() - interval ${days} day
      `;

      const [surfaceDailyResult, surfaceSummaryResult] = await Promise.all([
        queryPostHog(posthogHost, posthogProjectId, posthogApiKey, surfaceDailyCtrQuery),
        queryPostHog(posthogHost, posthogProjectId, posthogApiKey, surfaceSummaryQuery),
      ]);

      const surfaceDailyRows: [string, number, number, number][] = surfaceDailyResult?.results ?? [];
      const surfaceSummaryRow: [number, number, number, number] | undefined = surfaceSummaryResult?.results?.[0];
      const surfaceCtr = buildCtr(surfaceDailyRows, surfaceSummaryRow, 'surface_tagged');

      if (surfaceCtr.summary.sent > 0 || surfaceCtr.summary.clicked > 0) {
        return surfaceCtr;
      }

      const fallbackDailyCtrQuery = `
        SELECT
          toDate(timestamp) as day,
          countIf(event = 'Notification Sent') as sent,
          countIf(event = 'Notification Clicked') as clicked,
          countIf(event = 'Notification Dismissed') as dismissed
        FROM events
        WHERE event IN ('Notification Sent', 'Notification Clicked', 'Notification Dismissed')
          AND properties.$os_name = 'macOS'
          AND timestamp >= now() - interval ${days} day
        GROUP BY day
        ORDER BY day
      `;

      const fallbackSummaryQuery = `
        SELECT
          countIf(event = 'Notification Sent') as sent,
          countIf(event = 'Notification Clicked') as clicked,
          countIf(event = 'Notification Dismissed') as dismissed,
          count(DISTINCT if(event = 'Notification Clicked', distinct_id, null)) as unique_clickers
        FROM events
        WHERE event IN ('Notification Sent', 'Notification Clicked', 'Notification Dismissed')
          AND properties.$os_name = 'macOS'
          AND timestamp >= now() - interval ${days} day
      `;

      const [fallbackDailyResult, fallbackSummaryResult] = await Promise.all([
        queryPostHog(posthogHost, posthogProjectId, posthogApiKey, fallbackDailyCtrQuery),
        queryPostHog(posthogHost, posthogProjectId, posthogApiKey, fallbackSummaryQuery),
      ]);

      const fallbackDailyRows: [string, number, number, number][] = fallbackDailyResult?.results ?? [];
      const fallbackSummaryRow: [number, number, number, number] | undefined = fallbackSummaryResult?.results?.[0];
      return buildCtr(fallbackDailyRows, fallbackSummaryRow, 'all_notifications_fallback');
    };

    // Run counts, notifications, and CTR queries in parallel
    const [countResults, , floatingBarCtrResult] = await Promise.all([
      countsPromise,
      fetchNotifications(),
      fetchFloatingBarCtr().catch((error) => {
        console.error('Error fetching floating bar CTR from PostHog:', error);
        return null;
      }),
    ]);
    floatingBarCtr = floatingBarCtrResult;

    const [disabledSnap, totalSnap] = countResults;
    const disabledCount = disabledSnap.data().count;
    const totalUsers = totalSnap.data().count;
    const enabledCount = Math.max(totalUsers - disabledCount, 0);

    // Build daily data
    const dailyData = dateKeys.map(key => ({
      date: key,
      mentorSent: dayBuckets[key].mentorSent,
      marketplaceMentorSent: dayBuckets[key].marketplaceMentorSent,
      uniqueUsersMentor: dayBuckets[key].uniqueUsersMentor.size,
      uniqueUsersMarketplace: dayBuckets[key].uniqueUsersMarketplace.size,
    }));

    // Build weekly data
    const weekBuckets: Record<string, {
      mentorSent: number;
      marketplaceMentorSent: number;
      uniqueUsersMentor: Set<string>;
      uniqueUsersMarketplace: Set<string>;
    }> = {};

    for (const key of dateKeys) {
      const d = new Date(key + 'T00:00:00Z');
      const day = d.getUTCDay();
      const diff = d.getUTCDate() - day + (day === 0 ? -6 : 1);
      const weekStart = new Date(d);
      weekStart.setUTCDate(diff);
      const weekKey = weekStart.toISOString().split('T')[0];

      if (!weekBuckets[weekKey]) {
        weekBuckets[weekKey] = { mentorSent: 0, marketplaceMentorSent: 0, uniqueUsersMentor: new Set(), uniqueUsersMarketplace: new Set() };
      }

      weekBuckets[weekKey].mentorSent += dayBuckets[key].mentorSent;
      weekBuckets[weekKey].marketplaceMentorSent += dayBuckets[key].marketplaceMentorSent;
      dayBuckets[key].uniqueUsersMentor.forEach(u => weekBuckets[weekKey].uniqueUsersMentor.add(u));
      dayBuckets[key].uniqueUsersMarketplace.forEach(u => weekBuckets[weekKey].uniqueUsersMarketplace.add(u));
    }

    const weeklyData = Object.keys(weekBuckets).sort().map(weekKey => ({
      week: weekKey,
      mentorSent: weekBuckets[weekKey].mentorSent,
      marketplaceMentorSent: weekBuckets[weekKey].marketplaceMentorSent,
      uniqueUsersMentor: weekBuckets[weekKey].uniqueUsersMentor.size,
      uniqueUsersMarketplace: weekBuckets[weekKey].uniqueUsersMarketplace.size,
    }));

    const hourlyData = hourlyKeys.map(hk => ({
      hour: hk, // "2026-02-19T14"
      mentor: hourlyTimeline[hk].mentor,
      marketplace: hourlyTimeline[hk].marketplace,
      total: hourlyTimeline[hk].mentor + hourlyTimeline[hk].marketplace,
    }));

    return NextResponse.json({
      dailyData,
      weeklyData,
      hourlyData,
      floatingBarCtr,
      enabledDisabled: {
        enabled: enabledCount,
        disabled: disabledCount,
        total: totalUsers,
      },
    });
  } catch (error) {
    console.error('Error fetching notification stats:', error);
    return NextResponse.json(
      { error: 'Failed to fetch notification stats' },
      { status: 500 }
    );
  }
}
