import { describe, expect, it } from 'vitest';
import { groupActionItems } from '@/lib/actionItemGroups';
import type { ActionItem } from '@/types/conversation';

const NOW = new Date(2026, 0, 15, 9, 30);

function task(
  id: string,
  dueAt: Date | null,
  extra: Partial<ActionItem> = {},
): ActionItem {
  return {
    id,
    description: id,
    completed: false,
    due_at: dueAt ? dueAt.toISOString() : null,
    ...extra,
  };
}

const at = (day: number, hour = 12) => new Date(2026, 0, day, hour);

describe('groupActionItems', () => {
  it('keeps a task due later on the seventh day in This Week', () => {
    const groups = groupActionItems(
      [
        task('evening', at(22, 18)),
        task('midnight', at(22, 0)),
        task('eighth-day', at(23, 1)),
      ],
      NOW,
    );

    expect(groups.thisWeek.map((item) => item.id)).toEqual(['midnight', 'evening']);
    expect(groups.later.map((item) => item.id)).toEqual(['eighth-day']);
  });

  it('still peels today and tomorrow out of This Week', () => {
    const groups = groupActionItems(
      [
        task('late-today', at(15, 23)),
        task('tomorrow-night', at(16, 22)),
        task('day-after', at(17, 8)),
        task('overdue', at(14, 18)),
        task('undated', null),
        task('done', at(22, 18), {
          completed: true,
          completed_at: at(15, 12).toISOString(),
        }),
      ],
      NOW,
    );

    expect(groups.today.map((item) => item.id)).toEqual(['late-today']);
    expect(groups.tomorrow.map((item) => item.id)).toEqual(['tomorrow-night']);
    expect(groups.thisWeek.map((item) => item.id)).toEqual(['day-after']);
    expect(groups.overdue.map((item) => item.id)).toEqual(['overdue']);
    expect(groups.noDueDate.map((item) => item.id)).toEqual(['undated']);
    expect(groups.later).toEqual([]);
    expect(groups.completed.map((item) => item.id)).toEqual(['done']);
  });
});
