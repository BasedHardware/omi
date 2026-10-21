import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { dayKeyOf } from '@/lib/localDay';
import { summarizeMemoryActivity } from '@/lib/memoryActivity';

function memory(createdAt: Date) {
  return { created_at: createdAt.toISOString() };
}

describe('summarizeMemoryActivity', () => {
  // Pinned so the buckets are checked against a real offset, not the runner's,
  // which is UTC in CI where a UTC key and a local key agree.
  const hostTimezone = process.env.TZ;
  beforeAll(() => {
    process.env.TZ = 'Asia/Kolkata';
  });
  afterAll(() => {
    process.env.TZ = hostTimezone;
  });

  it('counts today in the last bar', () => {
    const now = new Date(2026, 8, 21, 10, 0);
    const { activityData } = summarizeMemoryActivity(
      [memory(new Date(2026, 8, 21, 9, 0)), memory(new Date(2026, 8, 21, 23, 30))],
      now,
    );

    expect(activityData).toHaveLength(30);
    expect(activityData.at(-1)).toEqual({ date: dayKeyOf(now), count: 2 });
  });

  it('keeps an evening memory on the day it was saved', () => {
    const now = new Date(2026, 8, 21, 10, 0);
    const lastNight = new Date(2026, 8, 20, 22, 15);

    const { activityData } = summarizeMemoryActivity([memory(lastNight)], now);
    const yesterday = activityData.find((day) => day.date === dayKeyOf(lastNight));

    expect(yesterday?.count).toBe(1);
  });

  it('reports this week and today separately', () => {
    const now = new Date(2026, 8, 21, 10, 0);
    const summary = summarizeMemoryActivity(
      [
        memory(new Date(2026, 8, 21, 9, 0)),
        memory(new Date(2026, 8, 18, 9, 0)),
        memory(new Date(2026, 7, 1, 9, 0)),
      ],
      now,
    );

    expect(summary.recentMemoriesCount).toBe(2);
    expect(summary.todayMemories).toHaveLength(1);
  });
});
