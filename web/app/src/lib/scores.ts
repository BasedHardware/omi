import type { ScorePeriod, ScoreTab, Scores } from '@/types/scores';

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
