import { describe, expect, it } from 'vitest';
import { allDayDue, taskDueDays } from '../taskDue';
import { groupActionItems } from '../actionItemGroups';
import type { ActionItem } from '@/types/conversation';

const due = { kind: 'date' as const, date: '2027-01-15', timezone: 'Asia/Ho_Chi_Minh' };

describe('date-only reminder consumer', () => {
  it('renders an all-day date without inventing a clock time', () => {
    expect(allDayDue(due, new Date('2027-01-14T18:00:00Z'))).toEqual({
      text: '2027-01-15 · All day',
      isOverdue: false,
      isToday: true,
    });
  });
  it('groups by the due timezone across the viewer midnight boundary', () => {
    const task: ActionItem = {
      id: 'synthetic-task',
      description: 'Renew the library card',
      completed: false,
      due_at: null,
      due,
    };
    expect(taskDueDays(task, new Date('2027-01-14T16:59:00Z'))).toBe(1);
    expect(groupActionItems([task], new Date('2027-01-14T18:00:00Z')).today).toEqual([
      task,
    ]);
    expect(groupActionItems([task], new Date('2027-01-15T18:00:00Z')).overdue).toEqual([
      task,
    ]);
  });
  it('keeps unresolved/undated and legacy timestamp tasks compatible', () => {
    expect(allDayDue({ kind: 'unresolved' })).toBeNull();
    expect(taskDueDays({ due_at: null })).toBeNull();
    expect(
      taskDueDays({ due_at: '2027-01-15T12:00:00Z' }, new Date('2027-01-15T11:00:00Z')),
    ).toBe(0);
  });
});

it('keeps date-only precision through snooze and a date-picker edit', async () => {
  const { editAllDayDue, snoozeAllDayDue } = await import('../taskDue');
  const snoozed = snoozeAllDayDue(due, 1, new Date('2027-01-15T18:00:00Z'));
  expect(snoozed.date).toBe('2027-01-17');
  expect(snoozed.kind).toBe('date');
  expect(snoozed.instant).toBeUndefined();
  expect(snoozed.year_basis).toBeNull();
  const edited = editAllDayDue(due, new Date(2027, 1, 2));
  expect(edited.date).toBe('2027-02-02');
  expect(edited.kind).toBe('date');
  expect(edited.year_basis).toBeNull();
});
