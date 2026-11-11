import { afterEach, describe, expect, it, vi } from 'vitest';
import { openCheckoutWindow } from '../checkoutWindow';

afterEach(() => vi.unstubAllGlobals());
describe('checkout browser launch', () => {
  it('reports a blocked or rejected launch without claiming checkout opened', () => {
    vi.stubGlobal(
      'open',
      vi.fn(() => null),
    );
    expect(openCheckoutWindow('https://checkout.stripe.test/pay')).toBe(false);
    vi.stubGlobal(
      'open',
      vi.fn(() => {
        throw new Error('browser denied');
      }),
    );
    expect(openCheckoutWindow('https://checkout.stripe.test/pay')).toBe(false);
  });
  it('keeps the existing URL and target for a successful launch', () => {
    const open = vi.fn(() => ({} as Window));
    vi.stubGlobal('open', open);
    expect(openCheckoutWindow('https://checkout.stripe.test/pay')).toBe(true);
    expect(open).toHaveBeenCalledWith('https://checkout.stripe.test/pay', '_blank');
  });
});
