import { describe, expect, it } from 'vitest';
import {
  describeScorePeriod,
  formatGoalMetric,
  formatMetricValue,
  goalProgressPercent,
  historyDelta,
  isGoalComplete,
  resolveDefaultTab,
  sortGoals,
  sortHistoryAscending,
  sparklinePoints,
} from '@/lib/goals';
import type { Goal, GoalHistoryEntry, Scores } from '@/types/goals';

function goal(overrides: Partial<Goal> = {}): Goal {
  return {
    id: 'goal-1',
    goal_id: 'goal-1',
    title: 'Read books',
    desired_outcome: 'Read books',
    status: 'background',
    source: 'user',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    goal_type: 'numeric',
    current_value: 0,
    target_value: 10,
    min_value: 0,
    max_value: 10,
    is_active: true,
    ...overrides,
  };
}

describe('goalProgressPercent', () => {
  it('measures progress from min_value, not from zero', () => {
    // 40 -> 80kg goal sitting at 40 has made no progress, even though 40/80 is half.
    const weight = goal({ min_value: 40, current_value: 40, target_value: 80 });

    expect(goalProgressPercent(weight)).toBe(0);
    expect(goalProgressPercent({ ...weight, current_value: 60 })).toBe(50);
    expect(goalProgressPercent({ ...weight, current_value: 80 })).toBe(100);
  });

  it('clamps below zero and above the target', () => {
    expect(goalProgressPercent(goal({ current_value: -5 }))).toBe(0);
    expect(goalProgressPercent(goal({ current_value: 25 }))).toBe(100);
  });

  it('treats a boolean goal as all or nothing', () => {
    const flag = goal({ goal_type: 'boolean', target_value: 1, max_value: 1 });

    expect(goalProgressPercent(flag)).toBe(0);
    expect(goalProgressPercent({ ...flag, current_value: 1 })).toBe(100);
  });

  it('does not divide by a zero span', () => {
    const degenerate = goal({ min_value: 5, target_value: 5, current_value: 5 });

    expect(goalProgressPercent(degenerate)).toBe(100);
    expect(goalProgressPercent({ ...degenerate, current_value: 1 })).toBe(0);
  });

  it('rounds to a whole percent', () => {
    expect(goalProgressPercent(goal({ current_value: 1, target_value: 3 }))).toBe(33);
  });
});

describe('isGoalComplete', () => {
  it('is true once current reaches target', () => {
    expect(isGoalComplete(goal({ current_value: 9 }))).toBe(false);
    expect(isGoalComplete(goal({ current_value: 10 }))).toBe(true);
    expect(isGoalComplete(goal({ current_value: 11 }))).toBe(true);
  });
});

describe('formatGoalMetric', () => {
  it('renders current over target with the unit', () => {
    expect(formatGoalMetric(goal({ current_value: 3, unit: 'books' }))).toBe(
      '3 / 10 books',
    );
  });

  it('omits the unit when there is none', () => {
    expect(formatGoalMetric(goal({ current_value: 3 }))).toBe('3 / 10');
  });

  it('describes boolean goals in words', () => {
    const flag = goal({ goal_type: 'boolean', target_value: 1 });

    expect(formatGoalMetric(flag)).toBe('Not yet');
    expect(formatGoalMetric({ ...flag, current_value: 1 })).toBe('Done');
  });
});

describe('formatMetricValue', () => {
  it('drops the trailing zero the backend floats carry', () => {
    expect(formatMetricValue(3)).toBe('3');
    expect(formatMetricValue(3.5)).toBe('3.5');
    expect(formatMetricValue(3.456)).toBe('3.46');
  });
});

describe('sortGoals', () => {
  it('puts focused goals first, in focus_rank order', () => {
    const sorted = sortGoals([
      goal({ id: 'background' }),
      goal({ id: 'second', status: 'focused', focus_rank: 1 }),
      goal({ id: 'first', status: 'focused', focus_rank: 0 }),
    ]);

    expect(sorted.map((entry) => entry.id)).toEqual(['first', 'second', 'background']);
  });

  it('ranks paused and ended goals below active ones', () => {
    const sorted = sortGoals([
      goal({ id: 'achieved', status: 'achieved' }),
      goal({ id: 'paused', status: 'paused' }),
      goal({ id: 'background' }),
    ]);

    expect(sorted.map((entry) => entry.id)).toEqual(['background', 'paused', 'achieved']);
  });

  it('breaks ties with the most recently updated goal', () => {
    const sorted = sortGoals([
      goal({ id: 'older', updated_at: '2026-01-01T00:00:00Z' }),
      goal({ id: 'newer', updated_at: '2026-06-01T00:00:00Z' }),
    ]);

    expect(sorted.map((entry) => entry.id)).toEqual(['newer', 'older']);
  });

  it('does not mutate the input array', () => {
    const input = [
      goal({ id: 'background' }),
      goal({ id: 'focused', status: 'focused' }),
    ];
    sortGoals(input);

    expect(input.map((entry) => entry.id)).toEqual(['background', 'focused']);
  });
});

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

describe('sortHistoryAscending', () => {
  const entry = (date: string, value: number): GoalHistoryEntry => ({
    date,
    value,
    recorded_at: `${date}T00:00:00Z`,
  });

  it('orders oldest first so a chart reads left to right', () => {
    const sorted = sortHistoryAscending([
      entry('2026-03-01', 3),
      entry('2026-01-01', 1),
      entry('2026-02-01', 2),
    ]);

    expect(sorted.map((point) => point.value)).toEqual([1, 2, 3]);
  });

  it('does not mutate the input array', () => {
    const input = [entry('2026-03-01', 3), entry('2026-01-01', 1)];
    sortHistoryAscending(input);

    expect(input.map((point) => point.value)).toEqual([3, 1]);
  });
});

describe('sparklinePoints', () => {
  const entry = (date: string, value: number): GoalHistoryEntry => ({
    date,
    value,
    recorded_at: `${date}T00:00:00Z`,
  });

  it('spreads x evenly and inverts y for SVG coordinates', () => {
    const points = sparklinePoints([
      entry('2026-01-01', 0),
      entry('2026-01-02', 5),
      entry('2026-01-03', 10),
    ]);

    expect(points).toEqual([
      { x: 0, y: 1 },
      { x: 0.5, y: 0.5 },
      { x: 1, y: 0 },
    ]);
  });

  it('sorts before projecting, so out-of-order input still reads forward', () => {
    const points = sparklinePoints([entry('2026-01-03', 10), entry('2026-01-01', 0)]);

    expect(points).toEqual([
      { x: 0, y: 1 },
      { x: 1, y: 0 },
    ]);
  });

  it('draws a flat series down the middle rather than dividing by zero', () => {
    const points = sparklinePoints([entry('2026-01-01', 4), entry('2026-01-02', 4)]);

    expect(points).toEqual([
      { x: 0, y: 0.5 },
      { x: 1, y: 0.5 },
    ]);
  });

  it('handles empty and single-point history', () => {
    expect(sparklinePoints([])).toEqual([]);
    expect(sparklinePoints([entry('2026-01-01', 7)])).toEqual([{ x: 0, y: 0.5 }]);
  });
});

describe('historyDelta', () => {
  const entry = (date: string, value: number): GoalHistoryEntry => ({
    date,
    value,
    recorded_at: `${date}T00:00:00Z`,
  });

  it('measures last minus first in date order', () => {
    expect(historyDelta([entry('2026-01-03', 9), entry('2026-01-01', 4)])).toBe(5);
  });

  it('reports a decline as negative', () => {
    expect(historyDelta([entry('2026-01-01', 9), entry('2026-01-03', 4)])).toBe(-5);
  });

  it('has nothing to compare with fewer than two points', () => {
    expect(historyDelta([])).toBeNull();
    expect(historyDelta([entry('2026-01-01', 4)])).toBeNull();
  });
});
