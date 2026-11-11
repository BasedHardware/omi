import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { getIdToken, auth, listeners } = vi.hoisted(() => ({
  getIdToken: vi.fn(),
  auth: { currentUser: null as any },
  listeners: new Set<(user: any) => void>(),
}));

vi.mock('@/lib/firebase', () => ({
  auth,
  onAuthStateChange: (callback: (user: any) => void) => {
    listeners.add(callback);
    return () => listeners.delete(callback);
  },
}));

import {
  claimReferralTrial as claimOwnedReferralTrial,
  referralMobilePlatform,
  referralDownloadURL,
  referralSignInProvider,
  parseReferralEnvironment,
  ReferralClaimError,
} from '@/lib/referrals';

const claimReferralTrial = (code: string, environment: 'prod' | 'dev', options = {}) =>
  claimOwnedReferralTrial(code, environment, { user: auth.currentUser, ...options });

describe('web referral handoff', () => {
  beforeEach(() => {
    getIdToken.mockReset();
    auth.currentUser = { uid: 'owner-a', getIdToken };
    listeners.clear();
    vi.unstubAllGlobals();
  });

  afterEach(() => vi.useRealTimers());

  it('accepts only the backend environments emitted by referral capture', () => {
    expect(parseReferralEnvironment('prod')).toBe('prod');
    expect(parseReferralEnvironment('dev')).toBe('dev');
    expect(parseReferralEnvironment('https://attacker.example')).toBeNull();
    expect(parseReferralEnvironment(null)).toBeNull();
  });

  it('uses native mobile stores only for a recognized phone platform', () => {
    expect(referralMobilePlatform('Mozilla iPhone')).toBe('ios');
    expect(referralMobilePlatform('Mozilla Android')).toBe('android');
    expect(referralMobilePlatform('Mozilla Macintosh')).toBeNull();
    expect(referralDownloadURL('ios')).toBe('https://apps.apple.com/app/id6502156163');
    expect(referralDownloadURL('android')).toContain(
      'play.google.com/store/apps/details?id=com.friend.ios',
    );
    expect(referralDownloadURL(null)).toBe('https://macos.omi.me');
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

  it('rejects Firebase B before React has rendered B without reading a token', async () => {
    const capturedA = auth.currentUser;
    auth.currentUser = { uid: 'owner-b', getIdToken: vi.fn() };
    const send = vi.fn();
    vi.stubGlobal('fetch', send);
    await expect(
      claimOwnedReferralTrial('ref1.test.code', 'prod', { user: capturedA }),
    ).rejects.toThrow('cancelled');
    expect(getIdToken).not.toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
  });

  it('rejects a live Firebase switch during token lookup without a React rerender', async () => {
    let release!: (token: string) => void;
    getIdToken.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    const send = vi.fn();
    vi.stubGlobal('fetch', send);
    const pending = claimReferralTrial('ref1.test.code', 'prod');
    auth.currentUser = { uid: 'owner-b', getIdToken: vi.fn() };
    release('token-a');
    await expect(pending).rejects.toThrow('cancelled');
    expect(send).not.toHaveBeenCalled();
    expect(listeners.size).toBe(0);
  });

  it('invalidates sign-out and same-UID reentry even with the same user object', async () => {
    let release!: (token: string) => void;
    getIdToken.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    const send = vi.fn();
    vi.stubGlobal('fetch', send);
    const owner = auth.currentUser;
    const pending = claimReferralTrial('ref1.test.code', 'prod');
    auth.currentUser = null;
    for (const listener of listeners) listener(null);
    auth.currentUser = owner;
    for (const listener of listeners) listener(owner);
    release('token-a');
    await expect(pending).rejects.toThrow('cancelled');
    expect(send).not.toHaveBeenCalled();
  });

  it('does not publish a late success after live ownership changes', async () => {
    getIdToken.mockResolvedValue('token-a');
    let release!: (value: Response) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise((resolve) => {
            release = resolve;
          }),
      ),
    );
    const pending = claimReferralTrial('ref1.test.code', 'prod');
    await Promise.resolve();
    auth.currentUser = { uid: 'owner-b', getIdToken: vi.fn() };
    release(new Response(JSON.stringify({ claimed: true, trial_days: 30 })));
    await expect(pending).rejects.toThrow('cancelled');
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

describe('referral provider identity', () => {
  it('uses only exact Firebase provider identifiers', () => {
    expect(referralSignInProvider(['apple.com'])).toBe('Apple');
    expect(referralSignInProvider(['google.com'])).toBe('Google');
    expect(referralSignInProvider([])).toBeNull();
    expect(referralSignInProvider(['apple.com', 'google.com'])).toBeNull();
  });
  it.each([
    'https://apple.com',
    'https://accounts.google.com',
    'https://evil.test/apple.com',
    'https://evil.test/?provider=google.com',
    'apple.com.evil.test',
    'google.com.evil.test',
    'evilapple.com',
    'evilgoogle.com',
    'accounts.apple.com',
    'accounts.google.com',
    'javascript:apple.com',
    'data:text/plain,google.com',
    'https://apple.com@evil.test',
    'https://google.com@evil.test',
    '//apple.com',
    'APPLE.COM',
    'google.com.',
    'password',
  ])('does not interpret %s as a provider identifier', (value) => {
    expect(referralSignInProvider([value])).toBeNull();
  });
});
