import type { ActionItem } from '@/types/conversation';
import { formatDateInputValue } from '@/lib/dateInput';

export interface TaskDueStatus {
  text: string;
  isOverdue: boolean;
  isToday: boolean;
}

/**
 * Whole-day difference between a due timestamp and `now`, both floored to
 * local midnight so a task due later today counts as 0 days, not -1.
 */
export function daysUntilDue(dueAt: string, now: Date = new Date()): number {
  const due = new Date(dueAt);
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);
  return Math.round((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

/**
 * Format days late/until due
 */
export function formatDueStatus(dueAt: string, now: Date = new Date()): TaskDueStatus {
  const diffDays = daysUntilDue(dueAt, now);
  const due = new Date(dueAt);

  if (diffDays < 0) {
    const daysLate = Math.abs(diffDays);
    return {
      text: daysLate === 1 ? '1 day late' : `${daysLate} days late`,
      isOverdue: true,
      isToday: false,
    };
  } else if (diffDays === 0) {
    return { text: 'Due today', isOverdue: false, isToday: true };
  } else if (diffDays === 1) {
    return { text: 'Due tomorrow', isOverdue: false, isToday: false };
  } else if (diffDays <= 7) {
    return {
      text: `Due ${due.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
      })}`,
      isOverdue: false,
      isToday: false,
    };
  } else {
    return {
      text: `Due ${due.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`,
      isOverdue: false,
      isToday: false,
    };
  }
}

/**
 * Compact variant for dense task rows.
 */
export function formatDueBadge(
  dueAt: string,
  now: Date = new Date(),
): { text: string; isOverdue: boolean } {
  const diffDays = daysUntilDue(dueAt, now);
  const due = new Date(dueAt);

  if (diffDays < 0) {
    return { text: `${Math.abs(diffDays)}d late`, isOverdue: true };
  } else if (diffDays === 0) {
    return { text: 'Today', isOverdue: false };
  } else if (diffDays === 1) {
    return { text: 'Tomorrow', isOverdue: false };
  } else if (diffDays <= 7) {
    return {
      text: due.toLocaleDateString('en-US', { weekday: 'short' }),
      isOverdue: false,
    };
  } else {
    return {
      text: due.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      isOverdue: false,
    };
  }
}

/** A calendar date is never decoded as a viewer-local due instant. */
export function allDayDue(
  due:
    | { kind: string; date?: string | null; timezone?: string | null }
    | null
    | undefined,
  now: Date = new Date(),
): TaskDueStatus | null {
  if (due?.kind !== 'date' || !due.date || !due.timezone) return null;
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: due.timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const part = (key: string) => parts.find((p) => p.type === key)?.value;
  const today = `${part('year')}-${part('month')}-${part('day')}`;
  return {
    text: `${due.date} · All day`,
    isOverdue: due.date < today,
    isToday: due.date === today,
  };
}

export function taskDueDays(
  task: {
    due_at?: string | null;
    due?: { kind: string; date?: string | null; timezone?: string | null } | null;
  },
  now: Date = new Date(),
): number | null {
  const due = task.due;
  if (due?.kind === 'date' && due.date && due.timezone) {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: due.timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(now);
    const value = (key: string) => Number(parts.find((p) => p.type === key)?.value);
    const [year, month, day] = due.date.split('-').map(Number);
    return Math.round(
      (Date.UTC(year, month - 1, day) -
        Date.UTC(value('year'), value('month') - 1, value('day'))) /
        86400000,
    );
  }
  return task.due_at ? daysUntilDue(task.due_at, now) : null;
}

export function editsDueAsDate(
  task: Pick<ActionItem, 'due' | 'due_at' | 'reminder_origin'>,
): boolean {
  return task.due?.kind === 'date' || (!!task.reminder_origin && !task.due_at);
}

export function editAllDayDue(
  due: ActionItem['due'],
  date: Date,
): NonNullable<ActionItem['due']> {
  const value = formatDateInputValue(date);
  const base =
    due?.kind === 'date'
      ? due
      : {
          kind: 'date' as const,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        };
  return { ...base, date: value, expression: value, year_basis: null };
}

export function snoozeAllDayDue(
  due: ActionItem['due'],
  days: number,
  now: Date = new Date(),
): NonNullable<ActionItem['due']> {
  if (due?.kind !== 'date' || !due.date) {
    const date = new Date(now);
    date.setDate(date.getDate() + days);
    return editAllDayDue(null, date);
  }
  const remaining = taskDueDays({ due }, now) ?? 0;
  const [year, month, day] = due.date!.split('-').map(Number);
  const value = new Date(Date.UTC(year, month - 1, day + days - Math.min(0, remaining)))
    .toISOString()
    .slice(0, 10);
  return { ...due, date: value, expression: value, year_basis: null };
}
