import { createElement, type ReactNode } from 'react';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

let query = '';
let authUser: { uid: string } | null = null;
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
    signInWithApple: vi.fn(),
    signInWithGoogle: vi.fn(),
  }),
}));

vi.mock('@/lib/firebase', () => ({
  isFirebaseAuthConfigured: false,
}));

vi.mock('@/lib/referrals', async () => ({
  ...(await vi.importActual<typeof import('@/lib/referrals')>('@/lib/referrals')),
  claimReferralTrial: referralHarness.claim,
  navigateToDesktopDownload: referralHarness.navigate,
  parseReferralEnvironment: (value: string | null) =>
    value === 'dev' || value === 'prod' ? value : null,
}));

vi.mock('@/lib/analytics/posthog', () => ({
  PostHogManager: { pageView: vi.fn(), track: vi.fn() },
}));

import { ReferralClaimError } from '@/lib/referrals';

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

    expect(markup).toContain('One free month of Omi Pro');
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

  it('a failed claim exposes a working retry without an automatic retry loop', async () => {
    query = 'referral=ref1.test.code&environment=prod';
    authUser = { uid: 'synthetic-user' };
    referralHarness.claim
      .mockRejectedValueOnce(new Error('fixture transport failed'))
      .mockResolvedValueOnce({ claimed: true, trial_days: 30 });
    const view = render(createElement(LoginClient));
    const retry = await view.findByRole('button', { name: 'Try again' });
    expect(referralHarness.claim).toHaveBeenCalledTimes(1);
    fireEvent.click(retry);
    await waitFor(() => expect(referralHarness.navigate).toHaveBeenCalledTimes(1));
    expect(referralHarness.claim).toHaveBeenCalledTimes(2);
  });

  it('a terminal claim rejection provides continuation without a misleading retry', async () => {
    query = 'referral=ref1.test.code&environment=prod';
    authUser = { uid: 'synthetic-user' };
    referralHarness.claim.mockRejectedValue(new ReferralClaimError('Rejected', false));
    const view = render(createElement(LoginClient));
    await view.findByText(
      'This referral could not be applied to your account. You can continue to Omi.',
    );
    expect(view.queryByRole('button', { name: 'Try again' })).toBeNull();
    expect(referralHarness.claim).toHaveBeenCalledTimes(1);
  });

  it('a late claim for an old account cannot redirect the new signed-in account', async () => {
    query = 'referral=ref1.test.code&environment=prod';
    let finish!: (value: { claimed: boolean; trial_days: number }) => void;
    authUser = { uid: 'synthetic-old-user' };
    referralHarness.claim
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      )
      .mockResolvedValueOnce({ claimed: false, trial_days: 0 });
    const view = render(createElement(LoginClient));
    await waitFor(() => expect(referralHarness.claim).toHaveBeenCalledTimes(1));
    authUser = { uid: 'synthetic-new-user' };
    view.rerender(createElement(LoginClient));
    await waitFor(() => expect(referralHarness.claim).toHaveBeenCalledTimes(2));
    finish({ claimed: true, trial_days: 30 });
    await Promise.resolve();
    expect(referralHarness.navigate).not.toHaveBeenCalled();
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
