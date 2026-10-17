import { createElement, type ReactNode } from 'react';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

let query = '';
let authUser: { uid: string } | null = null;
const signInHarness = vi.hoisted(() => ({ google: vi.fn(), apple: vi.fn() }));
const routerHarness = vi.hoisted(() => ({ push: vi.fn() }));
const referralHarness = vi.hoisted(() => ({
  claim: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: routerHarness.push }),
  useSearchParams: () => new URLSearchParams(query),
}));

vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) =>
    createElement('img', { src: props.src, alt: props.alt }),
}));

vi.mock('@tschk/moonshine-next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) =>
    createElement('a', { href }, children),
}));

vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: authUser,
    loading: false,
    signInWithApple: signInHarness.apple,
    signInWithGoogle: signInHarness.google,
    clearRedirectSignInError: vi.fn(),
  }),
}));

vi.mock('@/lib/firebase', () => ({
  isFirebaseAuthConfigured: true,
}));

vi.mock('@/lib/referrals', () => ({
  claimReferralTrial: referralHarness.claim,
  navigateToDesktopDownload: referralHarness.navigate,
  parseReferralEnvironment: (value: string | null) =>
    value === 'dev' || value === 'prod' ? value : null,
}));

vi.mock('@/lib/analytics/posthog', () => ({
  PostHogManager: { pageView: vi.fn(), track: vi.fn() },
}));

import { LoginClient } from '@/app/login/LoginClient';

describe('LoginClient geometry', () => {
  beforeEach(() => {
    query = '';
    authUser = null;
    referralHarness.claim.mockReset();
    referralHarness.navigate.mockReset();
  });

  afterEach(cleanup);

  it('renders fixed auth actions, an out-of-flow status lane, and desktop mark clearance', () => {
    const markup = renderToStaticMarkup(createElement(LoginClient));

    expect(markup.match(/\bh-12\b/g)).toHaveLength(2);
    expect(markup).toContain('role="status"');
    expect(markup).toContain('absolute inset-x-0 top-full mt-3 h-[72px] w-full');
    expect(markup).toContain(
      'aria-hidden="true" class="mb-16 hidden h-16 w-16 sm:block"',
    );
    expect(markup).not.toContain('min-h-[52px]');
  });

  it('shows the promised free month before a referred user signs up', () => {
    query = 'referral=ref1.test.code&environment=prod';

    const markup = renderToStaticMarkup(createElement(LoginClient));

    expect(markup).toContain('One free month of Pro');
    expect(markup).toContain('Create your account to claim it');
    expect(markup).toContain('text-center font-display text-2xl');
    expect(markup).toContain('Continue with Apple');
    expect(markup).toContain('Continue with Google');
  });

  it('claims once and downloads after authentication succeeds', async () => {
    query = 'referral=ref1.test.code&environment=prod';
    authUser = { uid: 'new-user' };
    referralHarness.claim.mockResolvedValue({ claimed: true, trial_days: 30 });

    const view = render(createElement(LoginClient));
    view.rerender(createElement(LoginClient));

    await waitFor(() => expect(referralHarness.claim).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(referralHarness.navigate).toHaveBeenCalledTimes(1));
  });

  it('does not download for an ineligible existing account', async () => {
    query = 'referral=ref1.test.code&environment=prod';
    authUser = { uid: 'existing-user' };
    referralHarness.claim.mockResolvedValue({ claimed: false, trial_days: 30 });

    const view = render(createElement(LoginClient));

    await waitFor(() =>
      expect(
        view.getByText('This free month is only available to new accounts.'),
      ).toBeTruthy(),
    );
    expect(referralHarness.navigate).not.toHaveBeenCalled();
  });
});

describe('LoginClient return path', () => {
  beforeEach(() => {
    routerHarness.push.mockReset();
    authUser = { uid: 'user-1' };
  });

  afterEach(() => {
    cleanup();
    authUser = null;
    query = '';
  });

  it('returns a signed-in reader to the page an item link asked for', async () => {
    query = 'next=%2Fconversations%3Fid%3Dabc';
    render(createElement(LoginClient));
    await waitFor(() =>
      expect(routerHarness.push).toHaveBeenCalledWith('/conversations?id=abc'),
    );
  });

  it('ignores a next that would leave the app', async () => {
    query = 'next=%2F%2Fevil.example';
    render(createElement(LoginClient));
    await waitFor(() => expect(routerHarness.push).toHaveBeenCalledWith('/home'));
  });

  it('ignores a next that normalizes into a protocol-relative URL', async () => {
    query = 'next=%2F.%2F%2Fevil.example';
    render(createElement(LoginClient));
    await waitFor(() => expect(routerHarness.push).toHaveBeenCalledWith('/home'));
  });
});

describe('LoginClient sign-in navigation timing', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
      })),
    });
    authUser = null;
    query =
      'next=%2Fitems%3Ftask%3D6zDh2tLd9O8JDbAVKezY%26task%3D3j79CowojdreNQv5k27J%26task%3D8fMv4K1jvc3eKsW4lVXF';
    routerHarness.push.mockReset();
    signInHarness.google.mockReset().mockResolvedValue(undefined);
    signInHarness.apple.mockReset().mockResolvedValue(undefined);
  });
  afterEach(cleanup);

  it.each(['Google', 'Apple'] as const)(
    'waits for the auth subscriber after %s resolves',
    async (provider) => {
      const view = render(createElement(LoginClient));
      fireEvent.click(view.getByRole('button', { name: `Sign in with ${provider}` }));
      await waitFor(() =>
        expect(
          signInHarness[provider.toLowerCase() as 'google' | 'apple'],
        ).toHaveBeenCalledTimes(1),
      );
      await waitFor(() =>
        expect(
          view.getByRole('button', { name: `Sign in with ${provider}` }),
        ).not.toBeDisabled(),
      );
      expect(routerHarness.push).not.toHaveBeenCalled();

      authUser = { uid: 'authenticated' };
      view.rerender(createElement(LoginClient));
      await waitFor(() =>
        expect(routerHarness.push).toHaveBeenCalledWith(
          '/items?task=6zDh2tLd9O8JDbAVKezY&task=3j79CowojdreNQv5k27J&task=8fMv4K1jvc3eKsW4lVXF',
        ),
      );
      expect(routerHarness.push).toHaveBeenCalledTimes(1);
    },
  );
});
