import { describe, it, expect } from 'vitest';
import { transformRetention } from '../route';

describe('transformRetention', () => {
  it('caps per-cohort retention at 100% when counts[N] > counts[0]', () => {
    const raw = {
      '2026-03-27T00:00:00': { counts: [10, 12], first: 20 },
    };
    const result = transformRetention(raw);
    expect(result.cohorts).toHaveLength(1);
    expect(result.cohorts[0].users).toBe(10);
    expect(result.cohorts[0].data[0].retention).toBe(100);
    expect(result.cohorts[0].data[1].retention).toBe(100); // 120% capped to 100%
  });

  it('preserves retention values at or below 100%', () => {
    const raw = {
      '2026-03-27T00:00:00': { counts: [20, 10, 5], first: 30 },
    };
    const result = transformRetention(raw);
    expect(result.cohorts[0].data[0].retention).toBe(100);
    expect(result.cohorts[0].data[1].retention).toBe(50);
    expect(result.cohorts[0].data[2].retention).toBe(25);
  });

  it('caps average retention when one cohort exceeds 100%', () => {
    // Cohort A: counts[1]=12 > counts[0]=10 → 120% capped to 100%
    // Cohort B: counts[1]=10 / counts[0]=20 → 50%
    // Average: (100 + 50) / 2 = 75, not (120 + 50) / 2 = 85
    const raw = {
      '2026-03-27T00:00:00': { counts: [10, 12], first: 20 },
      '2026-03-28T00:00:00': { counts: [20, 10], first: 30 },
    };
    const result = transformRetention(raw);
    expect(result.data[1].retention).toBe(75);
  });

  it('skips cohorts with counts[0] === 0', () => {
    const raw = {
      '2026-03-27T00:00:00': { counts: [0, 5], first: 10 },
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

  it('handles multiple days with mixed over/under 100%', () => {
    // Real-world scenario: macOS filter causes some days >100%
    const raw = {
      '2026-03-27T00:00:00': { counts: [6, 9, 3, 8], first: 15 },
    };
    const result = transformRetention(raw);
    const retentions = result.cohorts[0].data.map((d) => d.retention);
    expect(retentions[0]).toBe(100);       // 100%
    expect(retentions[1]).toBe(100);       // 150% capped
    expect(retentions[2]).toBe(50);        // 50%
    expect(retentions[3]).toBe(100);       // 133% capped
  });
});
