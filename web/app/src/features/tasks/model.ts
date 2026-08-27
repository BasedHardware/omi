import type { ActionItem, GroupedActionItems } from '@/types/conversation';

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
      text: `Due ${due.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}`,
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

export function emptyGroupedActionItems(): GroupedActionItems {
  return {
    overdue: [],
    today: [],
    tomorrow: [],
    thisWeek: [],
    later: [],
    noDueDate: [],
    completed: [],
  };
}

export function isSameLocalDay(date: Date, now: Date = new Date()): boolean {
  return (
    date.getDate() === now.getDate() &&
    date.getMonth() === now.getMonth() &&
    date.getFullYear() === now.getFullYear()
  );
}

export function isLocalTomorrow(date: Date, now: Date = new Date()): boolean {
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  return (
    date.getDate() === tomorrow.getDate() &&
    date.getMonth() === tomorrow.getMonth() &&
    date.getFullYear() === tomorrow.getFullYear()
  );
}

export function isLocalThisWeek(date: Date, now: Date = new Date()): boolean {
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const weekFromNow = new Date(today);
  weekFromNow.setDate(weekFromNow.getDate() + 7);
  return date >= today && date <= weekFromNow;
}

export function isLocalOverdue(date: Date, now: Date = new Date()): boolean {
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  return date < today;
}

/** Group action items by due window. Completed items are never placed in a due bucket. */
export function groupActionItems(
  items: ActionItem[],
  now: Date = new Date(),
): GroupedActionItems {
  if (!Array.isArray(items)) {
    return emptyGroupedActionItems();
  }

  const groups = emptyGroupedActionItems();

  for (const item of items) {
    if (item.completed) {
      groups.completed.push(item);
      continue;
    }

    if (!item.due_at) {
      groups.noDueDate.push(item);
      continue;
    }

    const dueDate = new Date(item.due_at);

    if (isLocalOverdue(dueDate, now)) {
      groups.overdue.push(item);
    } else if (isSameLocalDay(dueDate, now)) {
      groups.today.push(item);
    } else if (isLocalTomorrow(dueDate, now)) {
      groups.tomorrow.push(item);
    } else if (isLocalThisWeek(dueDate, now)) {
      groups.thisWeek.push(item);
    } else {
      groups.later.push(item);
    }
  }

  const sortByDueDate = (a: ActionItem, b: ActionItem) => {
    if (a.due_at && b.due_at) {
      return new Date(a.due_at).getTime() - new Date(b.due_at).getTime();
    }
    if (a.due_at) return -1;
    if (b.due_at) return 1;
    const aCreated = a.created_at ? new Date(a.created_at).getTime() : 0;
    const bCreated = b.created_at ? new Date(b.created_at).getTime() : 0;
    return bCreated - aCreated;
  };

  const sortByCreatedAt = (a: ActionItem, b: ActionItem) => {
    const aCreated = a.created_at ? new Date(a.created_at).getTime() : 0;
    const bCreated = b.created_at ? new Date(b.created_at).getTime() : 0;
    return bCreated - aCreated;
  };

  groups.overdue.sort(sortByDueDate);
  groups.today.sort(sortByDueDate);
  groups.tomorrow.sort(sortByDueDate);
  groups.thisWeek.sort(sortByDueDate);
  groups.later.sort(sortByDueDate);
  groups.noDueDate.sort(sortByCreatedAt);
  groups.completed.sort((a, b) => {
    const aCompleted = a.completed_at ? new Date(a.completed_at).getTime() : 0;
    const bCompleted = b.completed_at ? new Date(b.completed_at).getTime() : 0;
    return bCompleted - aCompleted;
  });

  return groups;
}

export function getTaskCountsForDate(
  items: ActionItem[],
  date: Date,
): { pending: number; completed: number } {
  if (!Array.isArray(items)) {
    return { pending: 0, completed: 0 };
  }

  const dateStr = date.toDateString();
  let pending = 0;
  let completed = 0;

  for (const item of items) {
    if (!item.due_at) continue;
    const itemDate = new Date(item.due_at).toDateString();
    if (itemDate === dateStr) {
      if (item.completed) {
        completed++;
      } else {
        pending++;
      }
    }
  }

  return { pending, completed };
}
