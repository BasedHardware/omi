import { describe, expect, it } from 'vitest';

import {
  RESUBSCRIBE_FIRST,
  EXISTING_SUBSCRIPTION,
  purchaseErrorMessage,
  renewalDateSeconds,
  yourPlanEndsOn,
  yourPlanWillRenewOn,
} from '@/lib/cancelPending';

describe('cancel pending purchase copy', () => {
  it('uses the approved sentences', () => {
    expect(yourPlanEndsOn('Plus', 'November 3, 2026')).toBe(
      'Your Plus plan ends November 3, 2026.',
    );
    expect(yourPlanWillRenewOn('Plus', 'November 3, 2026')).toBe(
      'Your Plus plan will renew on November 3, 2026.',
    );
    expect(RESUBSCRIBE_FIRST).toBe('Resubscribe first to change plans.');
  });

  it('recognizes a 409 and a billing timestamp', () => {
    const conflict = new Error('API error: 409 Conflict');
    expect(purchaseErrorMessage(conflict, 'upgrade')).toBe(RESUBSCRIBE_FIRST);
    expect(purchaseErrorMessage(conflict, 'checkout')).toBe(EXISTING_SUBSCRIPTION);
    expect(purchaseErrorMessage(new Error('API error: 400 Bad Request'), 'upgrade')).toBe(
      'An error occurred. Please try again.',
    );
    expect(renewalDateSeconds(1_762_128_000)).toBe(1_762_128_000);
    expect(renewalDateSeconds('1762128000')).toBe(1_762_128_000);
    expect(renewalDateSeconds(undefined, 10)).toBe(10);
  });
});
