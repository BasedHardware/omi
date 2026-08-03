import { describe, expect, it } from 'vitest';
import {
  historyDelta,
  sortGoals,
  sortHistoryAscending,
  sparklinePoints,
} from '@/lib/goals';
import type { Goal, GoalHistoryEntry } from '@/types/goals';

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
