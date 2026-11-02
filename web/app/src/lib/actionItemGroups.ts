import { daysUntilDue } from '@/lib/taskDue';
import type { ActionItem, GroupedActionItems } from '@/types/conversation';

function emptyGroups(): GroupedActionItems {
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

/**
 * Bucket tasks the way the Tasks hub labels them.
 *
 * Today and tomorrow are their own groups. This Week is the rest of the next
 * seven local calendar days (the same window `formatDueStatus` calls "this
 * week"), not a clock-time cutoff at midnight on the seventh day.
 */
export function groupActionItems(
  items: ActionItem[],
  now: Date = new Date(),
): GroupedActionItems {
  if (!Array.isArray(items)) {
    console.warn('groupActionItems: items is not an array', items);
    return emptyGroups();
  }

  const groups = emptyGroups();

  for (const item of items) {
    if (item.completed) {
      groups.completed.push(item);
      continue;
    }

    if (!item.due_at) {
      groups.noDueDate.push(item);
      continue;
    }

    const dueInDays = daysUntilDue(item.due_at, now);
    if (dueInDays < 0) {
      groups.overdue.push(item);
    } else if (dueInDays === 0) {
      groups.today.push(item);
    } else if (dueInDays === 1) {
      groups.tomorrow.push(item);
    } else if (dueInDays <= 7) {
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
