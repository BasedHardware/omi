import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));

vi.mock('@/lib/firebase', () => ({ getIdToken }));

import { claimReferralTrial, parseReferralEnvironment } from '@/lib/referrals';

describe('web referral handoff', () => {
  beforeEach(() => {
    getIdToken.mockReset();
    vi.unstubAllGlobals();
  });

  it('accepts only the backend environments emitted by referral capture', () => {
    expect(parseReferralEnvironment('prod')).toBe('prod');
    expect(parseReferralEnvironment('dev')).toBe('dev');
    expect(parseReferralEnvironment('https://attacker.example')).toBeNull();
    expect(parseReferralEnvironment(null)).toBeNull();
  });

  it('claims with the signed-in user token', async () => {
    getIdToken.mockResolvedValue('test-token');
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ claimed: true, trial_days: 30 }), {
          headers: { 'content-type': 'application/json' },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(claimReferralTrial('ref1.test.code', 'prod')).resolves.toEqual({
      claimed: true,
      trial_days: 30,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/referrals/claim',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    );
  });

  it('fails closed without an authenticated user', async () => {
    getIdToken.mockResolvedValue(null);
    await expect(claimReferralTrial('ref1.test.code', 'prod')).rejects.toThrow(
      'Not authenticated',
    );
  });
});
