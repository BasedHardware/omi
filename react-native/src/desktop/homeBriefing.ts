import {
  conversationGroupLabel,
  projectionTimestamp,
  type DesktopReadOutcomes,
} from '../desktopReadClient';
import type {ReadsPhase} from '../app/useDesktopReads';

export function homeBriefing(
  outcomes: DesktopReadOutcomes | null,
  phase: ReadsPhase,
) {
  if (phase === 'initial-loading' || phase === 'refreshing') {
    return {
      title: 'Getting your day ready',
      subtitle: 'Bringing your tasks and recent conversations into view.',
    };
  }
  if (
    phase !== 'ready' ||
    outcomes === null ||
    outcomes.tasks.status === 'error'
  ) {
    return {
      title: 'Your daily brief is waiting',
      subtitle: 'Refresh your context to see what needs attention.',
    };
  }
  const now = Date.now();
  const openTasks = outcomes.tasks.value.items
    .filter(task => !task.completed)
    .sort(
      (left, right) =>
        (left.dueAt ?? Infinity) - (right.dueAt ?? Infinity) ||
        left.sortOrder - right.sortOrder,
    );
  const next = openTasks[0];
  if (next !== undefined) {
    const due = next.dueAt === null ? null : new Date(next.dueAt);
    const timing =
      due === null
        ? 'On your list'
        : due.getTime() < now
        ? 'Overdue'
        : due.toDateString() === new Date(now).toDateString()
        ? 'Due today'
        : `Due ${due.toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
          })}`;
    const page = outcomes.tasks.value.page;
    const scope = page.complete && !page.hasMore ? '' : ' loaded';
    return {
      title: next.title,
      subtitle: `${timing} · ${openTasks.length} open task${
        openTasks.length === 1 ? '' : 's'
      }${scope}`,
    };
  }
  if (outcomes.conversations.status === 'success') {
    const latest = outcomes.conversations.value.items
      .filter(
        item =>
          !item.discarded &&
          !item.locked &&
          item.status === 'completed' &&
          item.title.trim() !== '',
      )
      .sort(
        (left, right) =>
          (projectionTimestamp(right) ?? -Infinity) -
          (projectionTimestamp(left) ?? -Infinity),
      )[0];
    if (latest !== undefined) {
      const timestamp = projectionTimestamp(latest);
      return {
        title: latest.title,
        subtitle:
          timestamp === null
            ? 'From your conversations'
            : `${conversationGroupLabel(
                new Date(timestamp).toISOString(),
                now,
              )} · From your conversations`,
      };
    }
  } else {
    return {
      title: 'Your daily brief is waiting',
      subtitle: 'Refresh your context to see what needs attention.',
    };
  }
  return {
    title: 'What’s on your mind?',
    subtitle: 'Capture a conversation or add a task to build your daily brief.',
  };
}
