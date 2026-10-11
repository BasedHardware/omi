import { t, tn, formatLocale } from '@/lib/i18n';

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
      text: tn(daysLate, '{count} day late', '{count} days late'),
      isOverdue: true,
      isToday: false,
    };
  } else if (diffDays === 0) {
    return { text: t('Due today'), isOverdue: false, isToday: true };
  } else if (diffDays === 1) {
    return { text: t('Due tomorrow'), isOverdue: false, isToday: false };
  } else if (diffDays <= 7) {
    return {
      text: t('Due {date}', {
        date: due.toLocaleDateString(formatLocale(), {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
        }),
      }),
      isOverdue: false,
      isToday: false,
    };
  } else {
    return {
      text: t('Due {date}', {
        date: due.toLocaleDateString(formatLocale(), { month: 'short', day: 'numeric' }),
      }),
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
    return { text: t('{count}d late', { count: Math.abs(diffDays) }), isOverdue: true };
  } else if (diffDays === 0) {
    return { text: t('Today'), isOverdue: false };
  } else if (diffDays === 1) {
    return { text: t('Tomorrow'), isOverdue: false };
  } else if (diffDays <= 7) {
    return {
      text: due.toLocaleDateString(formatLocale(), { weekday: 'short' }),
      isOverdue: false,
    };
  } else {
    return {
      text: due.toLocaleDateString(formatLocale(), { month: 'short', day: 'numeric' }),
      isOverdue: false,
    };
  }
}
