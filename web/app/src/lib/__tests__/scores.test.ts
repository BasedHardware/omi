import { describe, expect, it } from 'vitest';
import { describeScorePeriod, resolveDefaultTab } from '@/lib/scores';
import type { Scores } from '@/types/scores';

describe('resolveDefaultTab', () => {
  const scores = (defaultTab: string): Scores => ({
    daily: { score: 0, completed_tasks: 0, total_tasks: 0 },
    weekly: { score: 0, completed_tasks: 0, total_tasks: 0 },
    overall: { score: 0, completed_tasks: 0, total_tasks: 0 },
    default_tab: defaultTab,
    date: '2026-08-02',
  });

  it('honours a tab this client knows', () => {
    expect(resolveDefaultTab(scores('weekly'))).toBe('weekly');
  });

  it('falls back to daily for an unrecognised tab', () => {
    expect(resolveDefaultTab(scores('quarterly'))).toBe('daily');
  });
});

describe('describeScorePeriod', () => {
  it('reports the completed-over-total split', () => {
    expect(describeScorePeriod({ score: 50, completed_tasks: 2, total_tasks: 4 })).toBe(
      '2 of 4 tasks done',
    );
  });

  it('avoids an "0 of 0" reading when there is nothing to score', () => {
    expect(describeScorePeriod({ score: 0, completed_tasks: 0, total_tasks: 0 })).toBe(
      'No tasks yet',
    );
  });
});
