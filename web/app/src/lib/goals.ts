import type { Goal, ScorePeriod, ScoreTab, Scores } from '@/types/goals';

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

/**
 * The tab the server recommends, falling back to daily when it sends a value
 * this client does not know.
 */
export function resolveDefaultTab(scores: Scores): ScoreTab {
  const tab = scores.default_tab;
  return tab === 'daily' || tab === 'weekly' || tab === 'overall' ? tab : 'daily';
}

export function describeScorePeriod(period: ScorePeriod): string {
  if (period.total_tasks === 0) {
    return 'No tasks yet';
  }
  return `${period.completed_tasks} of ${period.total_tasks} tasks done`;
}
