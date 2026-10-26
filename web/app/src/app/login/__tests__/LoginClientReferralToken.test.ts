import { createElement } from 'react';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// A signed-in user whose ID token cannot be read right now (a transient Firebase
// failure surfaces as null, the same value as "signed out") must keep a manual
// Try Again, and a retry must never dispatch under an account that is no longer
// signed in. The real claimReferralTrial runs; only the token and fetch are faked.

let query = '';
let authUser: { uid: string } | null = null;
const harness = vi.hoisted(() => ({
  getIdToken: vi.fn(),
  navigate: vi.fn(),
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
  getIdToken: harness.getIdToken,
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
    authUser = { uid: 'synthetic-user' };
    harness.getIdToken.mockReset();
    harness.navigate.mockReset();
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

    authUser = { uid: 'synthetic-next-user' };
    view.rerender(createElement(LoginClient));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    releaseOld('token-old-account');
    await new Promise((resolve) => setTimeout(resolve, 20));

    const sent = fetchMock.mock.calls.map((call) => call[1].headers.Authorization);
    expect(sent).toEqual(['Bearer token-new-account']);
  });
});
