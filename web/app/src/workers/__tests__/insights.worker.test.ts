import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { dayKeyOf } from '@/lib/localDay';
import { computeInsights } from '@/workers/insights.worker';
import type { Memory } from '@/types/conversation';

function memory(createdAt: Date, id: string): Memory {
  return {
    id,
    content: `memory ${id}`,
    created_at: createdAt.toISOString(),
    category: 'core',
    tags: [],
  } as unknown as Memory;
}

function hoursOfDay(day: Date): Date[] {
  return Array.from(
    { length: 24 },
    (_, hour) => new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, 30),
  );
}

describe('insights day buckets', () => {
  // Pinned here so the keys are checked against a real offset rather than the
  // runner's, which is UTC in CI where a UTC key and a local key agree.
  const hostTimezone = process.env.TZ;
  beforeAll(() => {
    process.env.TZ = 'America/Los_Angeles';
  });
  afterAll(() => {
    process.env.TZ = hostTimezone;
  });

  it('puts every memory of a local day in that day of the activity calendar', () => {
    const today = new Date();
    const memories = hoursOfDay(today).map((at, index) => memory(at, `m-${index}`));

    const { activityCalendar } = computeInsights(memories);
    const todayCell = activityCalendar.find((day) => day.date === dayKeyOf(today));

    expect(todayCell?.count).toBe(24);
    expect(activityCalendar.at(-1)?.date).toBe(dayKeyOf(today));
  });

  it('counts a streak from the local day, not the UTC one', () => {
    const today = new Date();
    const lateToday = new Date(
      today.getFullYear(),
      today.getMonth(),
      today.getDate(),
      23,
      30,
    );
    const lateYesterday = new Date(
      today.getFullYear(),
      today.getMonth(),
      today.getDate() - 1,
      23,
      30,
    );

    const { summary } = computeInsights([
      memory(lateToday, 'm-1'),
      memory(lateYesterday, 'm-2'),
    ]);

    expect(summary?.currentStreak).toBe(2);
  });
});
