import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST } from '../route';
const good = {
  campaign_id: 'omi_pocket_match_v1',
  state: 'attributed',
  discount_percent: 10,
  checkout_url: 'https://www.omi.me/checkouts/local-fixture',
};
const req = (body: unknown, authorization = 'Bearer fixture') =>
  new Request('http://localhost/api/referrals/hardware', {
    method: 'POST',
    headers: { Authorization: authorization },
    body: JSON.stringify(body),
  });
afterEach(() => vi.unstubAllGlobals());
describe('hardware attribution proxy', () => {
  it.each([
    ['prod', 'https://api.omi.me'],
    ['dev', 'https://api.omiapi.com'],
  ])('pins %s and forwards only code', async (environment, origin) => {
    const send = vi.fn().mockResolvedValue(new Response(JSON.stringify(good)));
    vi.stubGlobal('fetch', send);
    expect((await POST(req({ code: 'ref2.a.b', environment }))).status).toBe(200);
    expect(send).toHaveBeenCalledWith(
      `${origin}/v2/users/me/referral/campaign/attribution`,
      expect.objectContaining({
        redirect: 'error',
        body: '{"code":"ref2.a.b"}',
        headers: expect.objectContaining({ Authorization: 'Bearer fixture' }),
      }),
    );
  });
  it.each([
    null,
    {},
    { code: 'ref1.a.b', environment: 'prod' },
    { code: 'ref2.a.b', environment: 'constructor' },
    { code: 'ref2.a.b', environment: '__proto__' },
    { code: 'ref2.a.b', environment: 'https://evil.test' },
    { code: 'ref2.a.b', environment: 'prod', uid: 'attacker' },
  ])('rejects invalid input %j without forwarding', async (body) => {
    const send = vi.fn();
    vi.stubGlobal('fetch', send);
    expect((await POST(req(body))).status).toBe(400);
    expect(send).not.toHaveBeenCalled();
  });
  it.each([
    ['campaign_disabled', 503],
    ['checkout_activation_required', 503],
    ['invalid_referral_code', 404],
    ['self_referral', 409],
    ['attribution_conflict', 409],
    ['account_unavailable', 409],
    ['checkout_unavailable', 503],
  ] as const)('preserves %s without leaking a URL', async (detail, status) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail, checkout_url: good.checkout_url }), {
          status,
        }),
      ),
    );
    const result = await POST(req({ code: 'ref2.a.b', environment: 'prod' }));
    expect(result.status).toBe(status);
    expect(await result.json()).toEqual({ detail });
    expect(result.headers.get('Cache-Control')).toBe('no-store');
  });
  it.each([
    { ...good, checkout_url: 'javascript:alert(1)' },
    { ...good, checkout_url: 'https://www.omi.me.evil.test/cart/a' },
    { ...good, discount_percent: 30 },
    { ...good, state: 'pending' },
  ])('turns malformed success into honest unavailable', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body))));
    const response = await POST(req({ code: 'ref2.a.b', environment: 'prod' }));
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ detail: 'checkout_unavailable' });
  });
});
