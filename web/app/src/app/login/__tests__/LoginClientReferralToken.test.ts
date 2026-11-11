import { createElement } from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// A signed-in user whose ID token cannot be read right now (a transient Firebase
// failure surfaces as null, the same value as "signed out") must keep a manual
// Try Again, and a retry must never dispatch under an account that is no longer
// signed in. The real claimReferralTrial runs; only the token and fetch are faked.

let query = '';
let authUser: { uid: string; getIdToken: typeof harness.getIdToken } | null = null;
const harness = vi.hoisted(() => ({
  getIdToken: vi.fn(),
  navigate: vi.fn(),
  authListeners: new Set<(user: { uid: string } | null) => void>(),
  unsubscribe: vi.fn(),
}));

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(query),
}));
vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) =>
    createElement('img', { src: props.src, alt: props.alt }),
}));
vi.mock('@tschk/moonshine-next/link', () => ({
  default: ({ href, children }: { href: string; children: unknown }) =>
    createElement('a', { href }, children as never),
}));
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: authUser,
    loading: false,
    signInWithApple: vi.fn(),
    signInWithGoogle: vi.fn(),
  }),
}));
vi.mock('@/lib/firebase', () => ({
  isFirebaseAuthConfigured: false,
  auth: {
    get currentUser() {
      return authUser;
    },
  },
  onAuthStateChange: (callback: (user: { uid: string } | null) => void) => {
    harness.authListeners.add(callback);
    return () => {
      harness.authListeners.delete(callback);
      harness.unsubscribe();
    };
  },
}));
vi.mock('@/lib/referrals', async () => ({
  ...(await vi.importActual<typeof import('@/lib/referrals')>('@/lib/referrals')),
  navigateToDesktopDownload: harness.navigate,
}));
vi.mock('@/lib/analytics/posthog', () => ({
  PostHogManager: { pageView: vi.fn(), track: vi.fn() },
}));

import { LoginClient } from '@/app/login/LoginClient';

const fetchMock = vi.fn();

describe('LoginClient referral with a temporary token failure', () => {
  beforeEach(() => {
    query = 'referral=ref1.test.code&environment=prod';
    authUser = { uid: 'synthetic-user', getIdToken: harness.getIdToken };
    harness.getIdToken.mockReset();
    harness.navigate.mockReset();
    harness.authListeners.clear();
    harness.unsubscribe.mockReset();
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ claimed: true, trial_days: 30 }), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('keeps Try again and succeeds on a manual retry without reloading', async () => {
    harness.getIdToken
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce('synthetic-token');
    const view = render(createElement(LoginClient));
    const retry = await view.findByRole('button', { name: 'Try again' });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(harness.getIdToken).toHaveBeenCalledTimes(1); // no automatic retry loop

    fireEvent.click(retry);
    await waitFor(() => expect(harness.navigate).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe(
      'Bearer synthetic-token',
    );
  });

  it('a retry whose token arrives after an account change never dispatches for the old account', async () => {
    let releaseOld!: (token: string) => void;
    harness.getIdToken
      .mockResolvedValueOnce(null)
      .mockImplementationOnce(() => new Promise((resolve) => (releaseOld = resolve)))
      .mockResolvedValue('token-new-account');
    const view = render(createElement(LoginClient));
    fireEvent.click(await view.findByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(harness.getIdToken).toHaveBeenCalledTimes(2));

    authUser = { uid: 'synthetic-next-user', getIdToken: harness.getIdToken };
    expect(harness.authListeners.size).toBe(1);
    for (const listener of harness.authListeners) listener(authUser);
    view.rerender(createElement(LoginClient));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    releaseOld('token-old-account');
    await new Promise((resolve) => setTimeout(resolve, 20));

    const sent = fetchMock.mock.calls.map((call) => call[1].headers.Authorization);
    expect(sent).toEqual(['Bearer token-new-account']);
  });

  it.each([
    ['token', 'switch'],
    ['dispatch', 'switch'],
    ['decode', 'switch'],
    ['token', 'signout'],
    ['dispatch', 'signout'],
    ['decode', 'signout'],
  ] as const)(
    'the auth listener invalidates %s pending across %s and A reentry',
    async (stage, transition) => {
      let releaseToken!: (token: string) => void;
      let releaseResponse!: (response: Response) => void;
      let releaseDecode!: (result: { claimed: boolean; trial_days: number }) => void;
      const json = vi.fn(() =>
        stage === 'decode'
          ? new Promise((resolve) => {
              releaseDecode = resolve;
            })
          : Promise.resolve({ claimed: true, trial_days: 30 }),
      );
      const response = { ok: true, json } as unknown as Response;
      harness.getIdToken.mockImplementation(() =>
        stage === 'token'
          ? new Promise((resolve) => {
              releaseToken = resolve;
            })
          : Promise.resolve('token-original-a'),
      );
      fetchMock.mockImplementation(() =>
        stage === 'dispatch'
          ? new Promise((resolve) => {
              releaseResponse = resolve;
            })
          : Promise.resolve(response),
      );
      const view = render(createElement(LoginClient));
      await waitFor(() => expect(harness.getIdToken).toHaveBeenCalledTimes(1));
      if (stage !== 'token')
        await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
      if (stage === 'decode') await waitFor(() => expect(json).toHaveBeenCalledTimes(1));
      expect(harness.authListeners.size).toBe(1);
      const originalA = authUser;

      // Restore the exact A object before resuming async work, without rerendering.
      // Live-currentUser and React owner checks then pass; only the listener latch
      // can prevent this old attempt from dispatching or publishing success.
      act(() => {
        authUser =
          transition === 'signout'
            ? null
            : { uid: 'user-b', getIdToken: harness.getIdToken };
        for (const listener of harness.authListeners) listener(authUser);
        authUser = originalA;
        for (const listener of harness.authListeners) listener(authUser);
      });
      await act(async () => {
        if (stage === 'token') releaseToken('token-original-a');
        if (stage === 'dispatch') releaseResponse(response);
        if (stage === 'decode') releaseDecode({ claimed: true, trial_days: 30 });
      });
      await view.findByText(
        'We could not confirm activation for this account. Check your plan in Omi using this same account.',
      );
      expect(harness.navigate).not.toHaveBeenCalled();
      expect(view.queryByText('Your free month is active')).toBeNull();
      expect(fetchMock).toHaveBeenCalledTimes(stage === 'token' ? 0 : 1);
      if (stage !== 'token')
        expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe(
          'Bearer token-original-a',
        );
      expect(harness.authListeners.size).toBe(0);
      expect(harness.unsubscribe).toHaveBeenCalledTimes(1);
    },
  );
});
