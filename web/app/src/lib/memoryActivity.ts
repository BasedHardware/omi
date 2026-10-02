import { dayKeyOf } from '@/lib/localDay';

export interface MemoryActivitySummary<T> {
  recentMemoriesCount: number;
  todayMemories: T[];
  activityData: Array<{ date: string; count: number }>;
}

const ACTIVITY_DAYS = 30;

/**
 * This week's count, today's memories and the 30 day activity bars, in one pass.
 *
 * Days are the viewer's local days: a memory saved in the evening belongs to
 * the day the user saved it on, and today's bar exists for every timezone.
 * [now] is injectable so the buckets are testable.
 */
export function summarizeMemoryActivity<T extends { created_at: string }>(
  memories: T[],
  now: Date = new Date(),
): MemoryActivitySummary<T> {
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const todayStr = today.toISOString();

  const sevenDaysAgo = new Date(now);
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const sevenDaysAgoStr = sevenDaysAgo.toISOString();

  const dayCounts: Record<string, number> = {};
  for (let i = ACTIVITY_DAYS - 1; i >= 0; i--) {
    const date = new Date(today);
    date.setDate(date.getDate() - i);
    dayCounts[dayKeyOf(date)] = 0;
  }

  let recentCount = 0;
  const todayMems: T[] = [];

  for (const m of memories) {
    if (m.created_at >= sevenDaysAgoStr) {
      recentCount++;
    }
    if (m.created_at >= todayStr) {
      todayMems.push(m);
    }
    const dateKey = dayKeyOf(new Date(m.created_at));
    if (dateKey in dayCounts) {
      dayCounts[dateKey]++;
    }
  }

  const activityData = Object.entries(dayCounts)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, count]) => ({ date, count }));

  return { recentMemoriesCount: recentCount, todayMemories: todayMems, activityData };
}
