import { afterEach, describe, expect, it, vi } from 'vitest';
import { openCheckoutWindow } from '../checkoutWindow';

const url = 'https://checkout.stripe.test/pay';

afterEach(() => vi.unstubAllGlobals());

describe('checkout browser launch', () => {
  it.each(['null', 'exception'])('reports a blocked %s launch', (failure) => {
    vi.stubGlobal(
      'open',
      vi.fn(() => {
        if (failure === 'exception') throw new Error('browser denied');
        return null;
      }),
    );
    expect(openCheckoutWindow(url)).toBeNull();
  });

  it('nulls the opener and keeps the URL/target without the noopener feature', () => {
    const checkout = { opener: window };
    const open = vi.fn(() => checkout);
    vi.stubGlobal('open', open);
    expect(openCheckoutWindow(url)).toBe(checkout);
    expect(open).toHaveBeenCalledExactlyOnceWith(url, '_blank');
    expect(checkout.opener).toBeNull();
  });

  it('still reports opened when browser policy rejects changing the opener', () => {
    const checkout = Object.defineProperty({}, 'opener', {
      set() {
        throw new Error('denied');
      },
    });
    vi.stubGlobal(
      'open',
      vi.fn(() => checkout),
    );
    expect(openCheckoutWindow(url)).toBe(checkout);
  });
});
