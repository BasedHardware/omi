import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({
  user: null as any,
  query: 'code=ref2.a.b&environment=prod',
  listeners: new Set<(u: any) => void>(),
  attribute: vi.fn(),
  google: vi.fn(),
  apple: vi.fn(),
}));
vi.mock('@/lib/firebase', () => ({
  auth: {
    get currentUser() {
      return h.user;
    },
  },
  isFirebaseAuthConfigured: true,
  onAuthStateChange: (cb: any) => {
    h.listeners.add(cb);
    return () => h.listeners.delete(cb);
  },
}));
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: h.user,
    loading: false,
    signInWithGoogle: h.google,
    signInWithApple: h.apple,
    clearRedirectSignInError: vi.fn(),
  }),
}));
vi.mock('@tschk/moonshine-next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(h.query),
}));
vi.mock('@/lib/hardwareReferral', async () => ({
  ...(await vi.importActual<typeof import('@/lib/hardwareReferral')>(
    '@/lib/hardwareReferral',
  )),
  attributeHardwareReferral: h.attribute,
}));
import { HardwareReferralClient } from '../HardwareReferralClient';
import { HardwareReferralError } from '@/lib/hardwareReferral';
const good = { checkout_url: 'https://www.omi.me/checkouts/fixture' };
beforeEach(() => {
  h.user = { uid: 'a' };
  h.query = 'code=ref2.a.b&environment=prod';
  h.attribute.mockReset();
  h.google.mockReset();
  h.apple.mockReset();
});
afterEach(cleanup);
describe('hardware recipient component', () => {
  it('retries 503 three times without showing checkout or a free month', async () => {
    h.attribute.mockRejectedValue(new HardwareReferralError('campaign_disabled', true));
    render(<HardwareReferralClient />);
    for (let i = 0; i < 3; i++) {
      await screen.findByText(/No discount has been confirmed/);
      expect(screen.queryByText('Continue to checkout')).toBeNull();
      expect(screen.queryByText(/30 days|free month/i)).toBeNull();
      if (i < 2) fireEvent.click(screen.getByText('Try again'));
    }
    expect(h.attribute).toHaveBeenCalledTimes(3);
  });
  it('invalidates stored checkout across A B A even when React batches auth events', async () => {
    h.attribute
      .mockResolvedValueOnce(good)
      .mockRejectedValue(new HardwareReferralError('campaign_disabled', true));
    render(<HardwareReferralClient />);
    await screen.findByText('Continue to checkout');
    act(() => {
      const a = h.user;
      h.user = { uid: 'b' };
      for (const cb of h.listeners) cb(h.user);
      h.user = a;
      for (const cb of h.listeners) cb(a);
    });
    await screen.findByText(/No discount has been confirmed/);
    expect(screen.queryByText('Continue to checkout')).toBeNull();
  });
  it('does not publish a stale result after unmount', async () => {
    let release!: (v: any) => void;
    h.attribute.mockImplementation(
      () =>
        new Promise((r) => {
          release = r;
        }),
    );
    const view = render(<HardwareReferralClient />);
    await waitFor(() => expect(h.attribute).toHaveBeenCalledTimes(1));
    const options = h.attribute.mock.calls[0][2];
    view.unmount();
    expect(options.isCurrent()).toBe(false);
    expect(options.signal.aborted).toBe(true);
    await act(async () => release(good));
    expect(h.listeners.size).toBe(0);
  });
  it.each(['Google', 'Apple'])(
    'keeps code and environment on the page through %s sign-in',
    async (provider) => {
      h.user = null;
      h.query = 'code=ref2.a.b&environment=dev';
      render(<HardwareReferralClient />);
      fireEvent.click(screen.getByText(`Continue with ${provider}`));
      await waitFor(() =>
        expect(provider === 'Google' ? h.google : h.apple).toHaveBeenCalledTimes(1),
      );
      expect(h.query).toBe('code=ref2.a.b&environment=dev');
    },
  );
  it('rejects missing or arbitrary environment before sign-in or attribution', () => {
    h.query = 'code=ref2.a.b&environment=https://evil.test';
    render(<HardwareReferralClient />);
    expect(screen.getByText('Referral unavailable')).toBeTruthy();
    expect(h.attribute).not.toHaveBeenCalled();
    expect(screen.queryByText('Continue to checkout')).toBeNull();
  });
});
