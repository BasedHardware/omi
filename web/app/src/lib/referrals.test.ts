import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { getIdToken } = vi.hoisted(() => ({ getIdToken: vi.fn() }));

vi.mock('@/lib/firebase', () => ({ getIdToken }));

import {
  claimReferralTrial,
  parseReferralEnvironment,
  ReferralClaimError,
} from '@/lib/referrals';

describe('web referral handoff', () => {
  beforeEach(() => {
    getIdToken.mockReset();
    vi.unstubAllGlobals();
  });

  afterEach(() => vi.useRealTimers());

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

  it('fails closed without a token but keeps the signed-in claim manually retryable', async () => {
    getIdToken.mockResolvedValue(null);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const failure = await claimReferralTrial('ref1.test.code', 'prod').catch((e) => e);
    expect(failure).toBeInstanceOf(ReferralClaimError);
    expect(failure.retryable).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('bounds token refresh and cannot dispatch after the deadline', async () => {
    vi.useFakeTimers();
    let release!: (token: string) => void;
    getIdToken.mockImplementation(
      () =>
        new Promise<string>((resolve) => {
          release = resolve;
        }),
    );
    const send = vi.fn();
    vi.stubGlobal('fetch', send);
    const result = claimReferralTrial('ref1.test.code', 'prod', { deadlineMs: 1000 });
    const rejected = expect(result).rejects.toThrow('timed out');
    await vi.advanceTimersByTimeAsync(1000);
    await rejected;
    release('synthetic-token');
    await Promise.resolve();
    expect(send).not.toHaveBeenCalled();
  });

  it('bounds a stalled response and aborts the actual request', async () => {
    vi.useFakeTimers();
    getIdToken.mockResolvedValue('synthetic-token');
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn((_url, options) => {
        signal = options.signal;
        return new Promise(() => {});
      }),
    );
    const result = claimReferralTrial('ref1.test.code', 'prod', { deadlineMs: 1000 });
    const rejected = expect(result).rejects.toThrow('timed out');
    await vi.advanceTimersByTimeAsync(1000);
    await rejected;
    expect(signal?.aborted).toBe(true);
  });

  it('an account replaced during token lookup cannot receive a referral POST', async () => {
    let current = true;
    let release!: (token: string) => void;
    getIdToken.mockImplementation(
      () =>
        new Promise<string>((resolve) => {
          release = resolve;
        }),
    );
    const send = vi.fn();
    vi.stubGlobal('fetch', send);
    const result = claimReferralTrial('ref1.test.code', 'prod', {
      isCurrent: () => current,
    });
    current = false;
    release('synthetic-token');
    await expect(result).rejects.toThrow('cancelled');
    expect(send).not.toHaveBeenCalled();
  });

  it('rejects malformed success and distinguishes retryable from terminal HTTP failures', async () => {
    getIdToken.mockResolvedValue('synthetic-token');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{"claimed":"yes","trial_days":30}')),
    );
    await expect(claimReferralTrial('ref1.test.code', 'prod')).rejects.toBeInstanceOf(
      ReferralClaimError,
    );
    for (const status of [400, 503]) {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => new Response('{}', { status })),
      );
      try {
        await claimReferralTrial('ref1.test.code', 'prod');
        throw new Error('Unexpected success');
      } catch (error) {
        expect((error as ReferralClaimError).retryable).toBe(status === 503);
      }
    }
  });
});
