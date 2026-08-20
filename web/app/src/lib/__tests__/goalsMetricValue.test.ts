import { describe, expect, it } from 'vitest';
import { formatMetricValue } from '@/lib/goals';

describe('formatMetricValue', () => {
  it('drops the trailing .0 the backend produces for whole numbers', () => {
    expect(formatMetricValue(10)).toBe('10');
    expect(formatMetricValue(10.0)).toBe('10');
    expect(formatMetricValue(0)).toBe('0');
  });

  it('keeps ordinary fractional targets readable', () => {
    expect(formatMetricValue(2.5)).toBe('2.5');
    expect(formatMetricValue(0.25)).toBe('0.25');
  });

  // The bug: this seeds a controlled target input, and the save path treats
  // `Number(input) !== goal.target_value` as an edit. Rounding here rewrote a
  // target the user never touched.
  it('round-trips a target with more than two decimals unchanged', () => {
    for (const value of [10.555, 0.001, 1.23456, 72.0625]) {
      expect(Number(formatMetricValue(value))).toBe(value);
    }
  });
});
