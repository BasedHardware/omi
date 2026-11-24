import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
const fixture = vi.hoisted(() => ({
  auth: { currentUser: null as any },
  listeners: new Set<(user: any) => void>(),
}));
vi.mock('@/lib/firebase', () => ({
  auth: fixture.auth,
  onAuthStateChange: (cb: any) => {
    fixture.listeners.add(cb);
    return () => fixture.listeners.delete(cb);
  },
}));
import { attributeHardwareReferral } from './hardwareReferral';
import { safeHardwareCheckout } from './hardwareReferralContract';
const good = {
  campaign_id: 'omi_pocket_match_v1',
  state: 'attributed',
  discount_percent: 10,
  checkout_url: 'https://www.omi.me/checkouts/fixture',
};
function churn() {
  const a = fixture.auth.currentUser;
  fixture.auth.currentUser = { uid: 'b' };
  for (const cb of fixture.listeners) cb(fixture.auth.currentUser);
  fixture.auth.currentUser = a;
  for (const cb of fixture.listeners) cb(a);
}
beforeEach(() => {
  fixture.auth.currentUser = {
    uid: 'a',
    getIdToken: vi.fn().mockResolvedValue('token-a'),
  };
  fixture.listeners.clear();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
describe('hardware checkout trust boundary', () => {
  it.each([
    'https://www.omi.me/checkouts/a',
    'https://88f4ed-c3.myshopify.com:443/cart/a',
  ])('accepts %s', (u) => expect(safeHardwareCheckout(u)).toBeTruthy());
  it.each([
    'javascript:alert(1)',
    'data:text/html,a',
    '//www.omi.me/cart/a',
    'http://www.omi.me/cart/a',
    'https://www.omi.me.evil.test/cart/a',
    'https://evil.test/www.omi.me/cart/a',
    'https://www.omi.me@evil.test/cart/a',
    'https://u:p@www.omi.me/cart/a',
    'https://www.omi.me:444/cart/a',
    'https://omi.me/cart/a',
    'https://omidotme.myshopify.com/cart/a',
    'https://www.omi.me/discount/a',
    'https://www.omi.me/cart/../../evil',
    'https://www.omi.me/Cart/a',
    'https://www.omi.me\\@evil.test/cart/a',
    'https://www.omi.me/cart/a\n',
  ])('rejects %s', (u) => expect(safeHardwareCheckout(u)).toBeNull());
});
describe('captured hardware referral auth', () => {
  it('uses the captured token and never client identity', async () => {
    const send = vi.fn().mockResolvedValue(new Response(JSON.stringify(good)));
    vi.stubGlobal('fetch', send);
    await expect(
      attributeHardwareReferral('ref2.a.b', 'dev', {
        user: fixture.auth.currentUser,
        isCurrent: () => true,
      }),
    ).resolves.toEqual(good);
    expect(send).toHaveBeenCalledWith(
      '/api/referrals/hardware',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-a' }),
        body: JSON.stringify({ code: 'ref2.a.b', environment: 'dev' }),
      }),
    );
  });
  it.each(['token', 'dispatch', 'decode'])('latches A B A at %s', async (stage) => {
    let release!: (v: any) => void;
    const pending = new Promise((r) => {
      release = r;
    });
    if (stage === 'token') fixture.auth.currentUser.getIdToken.mockReturnValue(pending);
    const send = vi.fn().mockImplementation(() =>
      stage === 'dispatch'
        ? pending
        : {
            ok: true,
            json: () => (stage === 'decode' ? pending : Promise.resolve(good)),
          },
    );
    vi.stubGlobal('fetch', send);
    const result = attributeHardwareReferral('ref2.a.b', 'prod', {
      user: fixture.auth.currentUser,
      isCurrent: () => true,
    });
    await Promise.resolve();
    await Promise.resolve();
    churn();
    release(
      stage === 'token'
        ? 'token-a'
        : stage === 'dispatch'
        ? new Response(JSON.stringify(good))
        : good,
    );
    await expect(result).rejects.toThrow('cancelled');
    if (stage === 'token') expect(send).not.toHaveBeenCalled();
    expect(fixture.listeners.size).toBe(0);
  });
  it('bounds stalled token lookup and suppresses late dispatch', async () => {
    vi.useFakeTimers();
    let release!: (v: string) => void;
    fixture.auth.currentUser.getIdToken.mockImplementation(
      () =>
        new Promise((r) => {
          release = r;
        }),
    );
    const send = vi.fn();
    vi.stubGlobal('fetch', send);
    const result = attributeHardwareReferral('ref2.a.b', 'prod', {
      user: fixture.auth.currentUser,
      isCurrent: () => true,
      deadlineMs: 50,
    });
    const rejected = expect(result).rejects.toThrow('checkout_unavailable');
    await vi.advanceTimersByTimeAsync(50);
    await rejected;
    release('late');
    await Promise.resolve();
    expect(send).not.toHaveBeenCalled();
  });
});
