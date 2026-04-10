import { describe, it, expect } from 'vitest';
import { transformRetention } from '../transform';

describe('transformRetention', () => {
  it('uses cohort.first as denominator for retention calculation', () => {
    const raw = {
      '2026-03-27T00:00:00': { counts: [7, 9], first: 12 },
    };
    const result = transformRetention(raw);
    expect(result.cohorts).toHaveLength(1);
    expect(result.cohorts[0].users).toBe(12); // first, not counts[0]
    expect(result.cohorts[0].data[0].retention).toBe(58.33); // 7/12 * 100
    expect(result.cohorts[0].data[1].retention).toBe(75); // 9/12 * 100
  });

  it('never produces >100% when counts[N] < first', () => {
    // Even though counts[1] > counts[0], retention stays ≤100% because denominator is first
    const raw = {
      '2026-03-27T00:00:00': { counts: [6, 9, 3], first: 10 },
    };
    const result = transformRetention(raw);
    const retentions = result.cohorts[0].data.map((d) => d.retention);
    expect(retentions[0]).toBe(60); // 6/10
    expect(retentions[1]).toBe(90); // 9/10
    expect(retentions[2]).toBe(30); // 3/10
    expect(retentions.every((r) => r <= 100)).toBe(true);
  });

  it('falls back to counts[0] when first is not provided', () => {
    const raw = {
      '2026-03-27T00:00:00': { counts: [20, 10, 5] },
    };
    const result = transformRetention(raw);
    expect(result.cohorts[0].users).toBe(20);
    expect(result.cohorts[0].data[0].retention).toBe(100);
    expect(result.cohorts[0].data[1].retention).toBe(50);
    expect(result.cohorts[0].data[2].retention).toBe(25);
  });

  it('computes average retention using first as denominator', () => {
    // Cohort A: first=12, counts[1]=9 → 75%
    // Cohort B: first=20, counts[1]=10 → 50%
    // Average: (75 + 50) / 2 = 62.5
    const raw = {
      '2026-03-27T00:00:00': { counts: [7, 9], first: 12 },
      '2026-03-28T00:00:00': { counts: [20, 10], first: 20 },
    };
    const result = transformRetention(raw);
    expect(result.data[1].retention).toBe(62.5);
  });

  it('skips cohorts with first === 0', () => {
    const raw = {
      '2026-03-27T00:00:00': { counts: [0, 5], first: 0 },
      '2026-03-28T00:00:00': { counts: [10, 5], first: 10 },
    };
    const result = transformRetention(raw);
    expect(result.cohorts).toHaveLength(1);
    expect(result.cohorts[0].date).toBe('2026-03-28');
    expect(result.totalUsers).toBe(10);
  });

  it('returns empty result for no cohort data', () => {
    const raw = {};
    const result = transformRetention(raw);
    expect(result.data).toEqual([]);
    expect(result.cohorts).toEqual([]);
    expect(result.totalCohorts).toBe(0);
    expect(result.totalUsers).toBe(0);
  });

  it('filters out non-cohort keys', () => {
    const raw = {
      '2026-03-27T00:00:00': { counts: [10, 5], first: 10 },
      request: { something: 'else' } as any,
    };
    const result = transformRetention(raw);
    expect(result.totalCohorts).toBe(1);
    expect(result.cohorts).toHaveLength(1);
  });

  it('totalUsers sums cohort.first values', () => {
    const raw = {
      '2026-03-27T00:00:00': { counts: [7, 3], first: 12 },
      '2026-03-28T00:00:00': { counts: [6, 2], first: 7 },
    };
    const result = transformRetention(raw);
    expect(result.totalUsers).toBe(19); // 12 + 7
  });
});
