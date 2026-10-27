import { describe, expect, it } from 'vitest';
import { decodePlan, planDisplayName, planGrantsPaidCapability } from '../user';

describe('canonical plan presentation', () => {
  it.each([
    ['basic', 'Free'],
    ['plus', 'Plus'],
    ['operator', 'Operator'],
    ['architect', 'Architect'],
    ['pro', 'Architect'],
    ['unlimited', 'Neo'],
    ['unlimited_v2', 'Omi Pro'],
    ['future_plan_123', 'Plan unavailable'],
  ])('%s is displayed as %s', (id, name) => {
    expect(planDisplayName(decodePlan(id))).toBe(name);
  });

  it('does not infer paid access from a future plan', () => {
    expect(planGrantsPaidCapability(decodePlan('future_plan_123'))).toBe(false);
  });
});
