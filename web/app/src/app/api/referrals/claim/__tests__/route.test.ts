import { afterEach, describe, expect, it, vi } from 'vitest';
import { POST, referralBackendOrigin } from '@/app/api/referrals/claim/route';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('referral claim proxy', () => {
  it('allows only the fixed production and development referral backends', () => {
    expect(referralBackendOrigin('prod')).toBe('https://api.omi.me');
    expect(referralBackendOrigin('dev')).toBe('https://api.omiapi.com');
    expect(referralBackendOrigin('https://attacker.example')).toBeNull();
  });

  it('forwards the authenticated claim to the selected backend', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ claimed: true, trial_days: 30 }), {
          headers: { 'content-type': 'application/json' },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      new Request('https://app.omi.me/api/referrals/claim', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer test-token',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ code: 'ref1.test.code', environment: 'dev' }),
      }),
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.omiapi.com/v1/users/me/referral/claim',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
        body: JSON.stringify({ code: 'ref1.test.code' }),
      }),
    );
  });

  it('rejects a caller-selected backend before forwarding credentials', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      new Request('https://app.omi.me/api/referrals/claim', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer test-token',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          code: 'ref1.test.code',
          environment: 'https://attacker.example',
        }),
      }),
    );

    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
