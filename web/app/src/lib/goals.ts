import type { Goal, GoalHistoryEntry } from '@/types/goals';

/**
 * Goal progress, completion, and labels come from `@/lib/goalVisuals`, ported
 * from the desktop apps. Re-exported here so hub code has one import.
 *
 * Note these are current/target, not min..target: desktop measures a 40->80kg
 * goal sitting at 40 as 50%, and a goal is also complete when the server has
 * archived it (`is_active === false`), not only when the value reaches target.
 */
export {
  isCompleted,
  progressColor,
  progressLabel,
  progressPct,
} from '@/lib/goalVisuals';
export { goalEmoji, DEFAULT_GOAL_EMOJI } from '@/lib/goalEmoji';

/** Trim the trailing `.0` the backend's float metrics produce for whole numbers. */
export function formatMetricValue(value: number): string {
  // `String` already drops a trailing `.0`; rounding here would rewrite the
  // value a controlled target input then saves back as a change the user
  // never made.
  return String(value);
}

/**
 * Display order: focused goals first by rank, then background, then anything
 * ended. Within a tier, most recently updated leads.
 */
export function sortGoals(goals: Goal[]): Goal[] {
  const tier = (goal: Goal): number => {
    if (goal.status === 'focused') return 0;
    if (goal.status === 'background') return 1;
    if (goal.status === 'paused') return 2;
    return 3;
  };

  return [...goals].sort((a, b) => {
    const tierDelta = tier(a) - tier(b);
    if (tierDelta !== 0) return tierDelta;

    if (a.status === 'focused' && b.status === 'focused') {
      const rankDelta = (a.focus_rank ?? 99) - (b.focus_rank ?? 99);
      if (rankDelta !== 0) return rankDelta;
    }

    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });
}

/** Oldest first, so a chart reads left to right in time order. */
export function sortHistoryAscending(history: GoalHistoryEntry[]): GoalHistoryEntry[] {
  return [...history].sort((a, b) => a.date.localeCompare(b.date));
}

export interface SparklinePoint {
  x: number;
  y: number;
}

/**
 * Project history values onto a 0..1 box for a sparkline.
 *
 * `y` is inverted so 0 is the top, matching SVG coordinates. A flat series has
 * no range to scale against and is drawn down the middle rather than pinned to
 * an edge.
 */
export function sparklinePoints(history: GoalHistoryEntry[]): SparklinePoint[] {
  const ordered = sortHistoryAscending(history);
  if (ordered.length === 0) return [];
  if (ordered.length === 1) return [{ x: 0, y: 0.5 }];

  const values = ordered.map((entry) => entry.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;

  return ordered.map((entry, index) => ({
    x: index / (ordered.length - 1),
    y: span === 0 ? 0.5 : 1 - (entry.value - min) / span,
  }));
}

/** Net change across the recorded window, or null when there is nothing to compare. */
export function historyDelta(history: GoalHistoryEntry[]): number | null {
  const ordered = sortHistoryAscending(history);
  if (ordered.length < 2) return null;
  return ordered[ordered.length - 1].value - ordered[0].value;
}
