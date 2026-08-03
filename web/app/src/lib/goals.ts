import type { Goal, GoalHistoryEntry } from '@/types/goals';

/**
 * How far a goal has come, 0..100.
 *
 * Progress is measured from `min_value` to `target_value`, so a goal that
 * starts at 40kg and targets 80kg reads 0% at 40, not 50%. A target equal to
 * the floor has nothing to measure, so it reads complete once reached.
 */
export function goalProgressPercent(goal: Goal): number {
  const { current_value: current, target_value: target, min_value: min } = goal;

  if (goal.goal_type === 'boolean') {
    return current >= target ? 100 : 0;
  }

  const span = target - min;
  if (span <= 0) {
    return current >= target ? 100 : 0;
  }

  const ratio = (current - min) / span;
  return Math.max(0, Math.min(100, Math.round(ratio * 100)));
}

export function isGoalComplete(goal: Goal): boolean {
  return goal.current_value >= goal.target_value;
}

/** Human-readable progress, e.g. `3 / 10 books` or `Done`. */
export function formatGoalMetric(goal: Goal): string {
  if (goal.goal_type === 'boolean') {
    return isGoalComplete(goal) ? 'Done' : 'Not yet';
  }

  const unit = goal.unit ? ` ${goal.unit}` : '';
  return `${formatMetricValue(goal.current_value)} / ${formatMetricValue(goal.target_value)}${unit}`;
}

/** Trim the trailing `.0` the backend's float metrics produce for whole numbers. */
export function formatMetricValue(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(2)));
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
