import { describe, expect, it } from 'vitest';
import { groupActionItems } from '../model';
import type { ActionItem } from '@/types/conversation';

const NOW = new Date(2026, 0, 15, 9, 30);

function item(overrides: Partial<ActionItem>): ActionItem {
  return {
    id: '1',
    description: 'task',
    completed: false,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  } as ActionItem;
}

describe('groupActionItems', () => {
  it('puts completed items only in completed, even when they have a due date', () => {
    const grouped = groupActionItems(
      [item({ id: 'c', completed: true, due_at: new Date(2026, 0, 10).toISOString() })],
      NOW,
    );
    expect(grouped.completed).toHaveLength(1);
    expect(grouped.overdue).toHaveLength(0);
  });

  it('buckets pending items by due window', () => {
    const grouped = groupActionItems(
      [
        item({ id: 'overdue', due_at: new Date(2026, 0, 10, 12).toISOString() }),
        item({ id: 'today', due_at: new Date(2026, 0, 15, 18).toISOString() }),
        item({ id: 'none' }),
      ],
      NOW,
    );
    expect(grouped.overdue.map((i) => i.id)).toEqual(['overdue']);
    expect(grouped.today.map((i) => i.id)).toEqual(['today']);
    expect(grouped.noDueDate.map((i) => i.id)).toEqual(['none']);
  });
});
