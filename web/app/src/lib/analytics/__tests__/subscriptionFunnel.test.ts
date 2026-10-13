import { beforeEach, describe, expect, it, vi } from 'vitest';

const track = vi.fn();

vi.mock('@/lib/analytics/posthog', () => ({
  PostHogManager: { track: (...args: unknown[]) => track(...args) },
}));

import {
  subscriptionIntervalWire,
  subscriptionPlanWire,
  trackPaywallOpened,
  trackUpgradeSucceeded,
} from '@/lib/analytics/subscriptionFunnel';

describe('subscription funnel wires', () => {
  beforeEach(() => {
    track.mockClear();
  });

  it('collapses legacy plan and interval aliases onto the closed vocabulary', () => {
    expect(subscriptionPlanWire('pro')).toBe('unknown');
    expect(subscriptionPlanWire('free')).toBe('basic');
    expect(subscriptionPlanWire('not-a-plan')).toBe('unknown');
    expect(subscriptionIntervalWire('yearly')).toBe('year');
    expect(subscriptionIntervalWire('Annual')).toBe('year');
    expect(subscriptionIntervalWire('Plus Yearly Monthly')).toBe('year');
  });

  it('emits the paywall and the attributed checkout success', () => {
    trackPaywallOpened('web_plans', 'plus');
    trackUpgradeSucceeded('plus', 'month');

    expect(track.mock.calls.map((call) => call[0])).toEqual([
      'Paywall Opened',
      'Upgrade Succeeded Attributed',
      'Upgrade Succeeded',
    ]);
    expect(track.mock.calls[0][1]).toEqual({ source: 'web_plans', current_plan: 'plus' });
    expect(track.mock.calls[1][1]).toEqual({ plan: 'plus', billing_interval: 'month' });
  });
});
