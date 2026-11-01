import { afterEach, describe, expect, it, vi } from 'vitest';

import { groupNotificationsByDate } from '@/lib/notificationGroups';
import type { OmiNotification } from '@/types/notification';

function notification(id: string, timestamp: string): OmiNotification {
  return {
    id,
    type: 'announcement',
    title: id,
    body: id,
    timestamp,
    read: false,
  };
}

function labels(items: OmiNotification[], now: Date): { label: string; ids: string[] }[] {
  return groupNotificationsByDate(items, now).map((group) => ({
    label: group.label,
    ids: group.notifications.map((item) => item.id),
  }));
}

/** Local calendar length in hours. Proves the pinned zone is in effect. */
function dayHours(year: number, monthIndex: number, day: number): number {
  return (
    (new Date(year, monthIndex, day + 1).getTime() -
      new Date(year, monthIndex, day).getTime()) /
    3_600_000
  );
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('groupNotificationsByDate', () => {
  it('keeps today, yesterday, and earlier in that order', () => {
    vi.stubEnv('TZ', 'UTC');
    const now = new Date('2026-06-15T15:00:00Z');

    expect(
      labels(
        [
          notification('earlier', '2026-06-13T18:00:00Z'),
          notification('today-late', '2026-06-15T22:00:00Z'),
          notification('yesterday', '2026-06-14T01:00:00Z'),
          notification('today-early', '2026-06-15T00:30:00Z'),
        ],
        now,
      ),
    ).toEqual([
      { label: 'Today', ids: ['today-late', 'today-early'] },
      { label: 'Yesterday', ids: ['yesterday'] },
      { label: 'Earlier', ids: ['earlier'] },
    ]);
  });

  it('drops empty groups and parks an unparseable timestamp in Earlier', () => {
    vi.stubEnv('TZ', 'UTC');

    expect(
      labels([notification('bad', 'not-a-date')], new Date('2026-06-15T15:00:00Z')),
    ).toEqual([{ label: 'Earlier', ids: ['bad'] }]);
    expect(groupNotificationsByDate([], new Date('2026-06-15T15:00:00Z'))).toEqual([]);
  });

  describe('across a daylight-saving change', () => {
    // CI runs in UTC, which never changes its clocks. New York's Sunday
    // 2026-03-08 lasts 23 h and Sunday 2026-11-01 lasts 25 h.

    it('files Sunday under Yesterday on the Monday after clocks spring forward', () => {
      vi.stubEnv('TZ', 'America/New_York');
      expect(dayHours(2026, 2, 8)).toBe(23);

      expect(
        labels(
          [
            notification('today', '2026-03-09T16:00:00Z'),
            notification('sunday', '2026-03-08T16:00:00Z'),
            notification('friday', '2026-03-06T16:00:00Z'),
          ],
          new Date('2026-03-09T16:00:00Z'),
        ),
      ).toEqual([
        { label: 'Today', ids: ['today'] },
        { label: 'Yesterday', ids: ['sunday'] },
        { label: 'Earlier', ids: ['friday'] },
      ]);
    });

    it('files Sunday under Yesterday on the Monday after clocks fall back', () => {
      vi.stubEnv('TZ', 'America/New_York');
      expect(dayHours(2026, 10, 1)).toBe(25);

      expect(
        labels(
          [
            notification('sunday-early', '2026-11-01T05:30:00Z'),
            notification('sunday-late', '2026-11-02T03:30:00Z'),
            notification('saturday', '2026-10-31T16:00:00Z'),
          ],
          new Date('2026-11-02T16:00:00Z'),
        ),
      ).toEqual([
        { label: 'Yesterday', ids: ['sunday-early', 'sunday-late'] },
        { label: 'Earlier', ids: ['saturday'] },
      ]);
    });
  });
});
