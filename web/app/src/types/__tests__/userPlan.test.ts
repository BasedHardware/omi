import { describe, expect, it } from 'vitest';
import {
  CATALOG_PLAN_IDS,
  decodePlan,
  encodePlan,
  planDisplayName,
  planGrantsPaidCapability,
} from '@/types/user';

const PLAN_FIXTURES = [...CATALOG_PLAN_IDS, 'pro', 'future_plan_123'] as const;

describe('subscription plan wire decoding', () => {
  it('decodes every catalog identity and the retained pro alias', () => {
    for (const raw of [...CATALOG_PLAN_IDS, 'pro']) {
      const decoded = decodePlan(raw);

      expect(decoded.kind).toBe('known');
      expect(decoded.raw).toBe(raw);
      expect(encodePlan(decoded)).toBe(raw);
    }

    expect(decodePlan('pro')).toEqual({ kind: 'known', id: 'architect', raw: 'pro' });
  });

  it('keeps future values lossless, neutral, and capability-safe', () => {
    const decoded = decodePlan('future_plan_123');

    expect(decoded).toEqual({ kind: 'unknown', raw: 'future_plan_123' });
    expect(encodePlan(decoded)).toBe('future_plan_123');
    expect(planDisplayName(decoded)).toBe('Plan unavailable');
    expect(planGrantsPaidCapability(decoded)).toBe(false);
  });

  it('does not throw or turn malformed values into Basic', () => {
    for (const raw of [
      undefined,
      null,
      '',
      123,
      { plan: 'future_plan_123' },
      'constructor',
      'toString',
      '__proto__',
    ]) {
      expect(() => decodePlan(raw)).not.toThrow();
      expect(decodePlan(raw).kind).toBe('unknown');
      expect(decodePlan(raw)).not.toEqual({ kind: 'known', id: 'basic', raw: 'basic' });
    }
  });

  it('covers the complete fixture set used by the client contract', () => {
    expect(PLAN_FIXTURES).toEqual([
      'basic',
      'plus',
      'unlimited',
      'unlimited_v2',
      'operator',
      'architect',
      'pro',
      'future_plan_123',
    ]);
  });
});
