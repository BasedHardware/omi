'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from '@tschk/moonshine-next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { auth, isFirebaseAuthConfigured, onAuthStateChange } from '@/lib/firebase';
import { parseReferralEnvironment } from '@/lib/referrals';
import {
  isHardwareReferralCode,
  safeHardwareCheckout,
} from '@/lib/hardwareReferralContract';
import {
  attributeHardwareReferral,
  HardwareReferralError,
  hardwareReferralMessage,
  navigateToHardwareCheckout,
} from '@/lib/hardwareReferral';

export function HardwareReferralClient() {
  const {
    user,
    loading,
    signInWithGoogle,
    signInWithApple,
    redirectSignInError,
    clearRedirectSignInError,
  } = useAuth();
  const params = useSearchParams();
  const code = params.get('code');
  const environment = parseReferralEnvironment(params.get('environment'));
  const valid = isHardwareReferralCode(code) && environment !== null;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkout, setCheckout] = useState<{ url: string; generation: number } | null>(
    null,
  );
  const [retryable, setRetryable] = useState(true);
  const boundary = useRef({ user, code, environment, generation: 0, mounted: false });
  const request = useRef<AbortController | null>(null);
  const started = useRef<number | null>(null);
  // A generation never becomes current again, even if React batches A -> B -> A.
  if (
    boundary.current.user !== user ||
    boundary.current.code !== code ||
    boundary.current.environment !== environment
  ) {
    boundary.current = {
      ...boundary.current,
      user,
      code,
      environment,
      generation: boundary.current.generation + 1,
    };
    request.current?.abort();
  }
  const generation = boundary.current.generation;
  useEffect(() => {
    boundary.current.mounted = true;
    let observed = auth?.currentUser;
    const unsubscribe = onAuthStateChange((next) => {
      if (next !== observed) {
        observed = next;
        boundary.current.generation++;
        request.current?.abort();
        setCheckout(null);
        setBusy(false);
        setError(null);
      }
    });
    return () => {
      boundary.current.mounted = false;
      boundary.current.generation++;
      request.current?.abort();
      unsubscribe();
    };
  }, []);

  async function prepareCheckout() {
    if (!user || !valid || started.current === generation || auth?.currentUser !== user)
      return;
    started.current = generation;
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    const current = () =>
      boundary.current.mounted &&
      boundary.current.generation === generation &&
      auth?.currentUser === user &&
      !controller.signal.aborted;
    setBusy(true);
    setError(null);
    setCheckout(null);
    try {
      const result = await attributeHardwareReferral(code, environment, {
        user,
        isCurrent: current,
        signal: controller.signal,
      });
      if (current()) setCheckout({ url: result.checkout_url, generation });
    } catch (failure) {
      if (!current()) return;
      setRetryable(!(failure instanceof HardwareReferralError) || failure.retryable);
      setError(
        hardwareReferralMessage(
          failure instanceof HardwareReferralError
            ? failure.detail
            : 'checkout_unavailable',
        ),
      );
    } finally {
      if (current()) setBusy(false);
    }
  }

  useEffect(() => {
    setError(null);
    setCheckout(null);
    setBusy(false);
    setRetryable(true);
    if (!loading && user && valid) void prepareCheckout();
    // Each account/link generation gets one automatic attempt; retries are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generation, loading]);

  async function signIn(provider: 'Google' | 'Apple') {
    setBusy(true);
    setError(null);
    clearRedirectSignInError();
    try {
      // Firebase returns redirects to this exact URL, preserving code + environment.
      await (provider === 'Google' ? signInWithGoogle() : signInWithApple());
    } catch {
      setError(`Could not sign in with ${provider}. Please try again.`);
    } finally {
      if (boundary.current.mounted) setBusy(false);
    }
  }

  const ready =
    checkout?.generation === generation && auth?.currentUser === user ? checkout : null;
  const button =
    'flex h-12 w-full items-center justify-center rounded-lg bg-white px-5 font-medium text-black hover:bg-gray-100 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white';
  return (
    <main className="flex min-h-[100svh] items-center justify-center bg-black px-5 py-12 text-center">
      <div className="w-full max-w-sm">
        <p className="mb-6 text-sm text-text-tertiary">omi</p>
        <h1 className="font-display text-2xl font-semibold text-text-primary">
          {valid && !error ? 'Get 10% off Omi hardware' : 'Referral unavailable'}
        </h1>
        <p className="mt-3 text-sm text-text-tertiary">
          {!valid
            ? 'This referral link is invalid or missing its environment. Ask your friend for a new link.'
            : error
            ? 'Checkout could not be prepared for this account.'
            : !user
            ? 'Sign in to continue with your friend’s referral.'
            : ready
            ? 'Your referral checkout is ready. Review your discount at checkout.'
            : 'Confirming your referral for this account.'}
        </p>
        {valid && (
          <div className="mt-6 space-y-3">
            {loading ? (
              <p role="status" className="text-sm text-text-tertiary">
                Checking sign-in...
              </p>
            ) : !user ? (
              <>
                <button
                  className={button}
                  disabled={busy || !isFirebaseAuthConfigured}
                  onClick={() => void signIn('Apple')}
                >
                  Continue with Apple
                </button>
                <button
                  className={button}
                  disabled={busy || !isFirebaseAuthConfigured}
                  onClick={() => void signIn('Google')}
                >
                  Continue with Google
                </button>
                {!isFirebaseAuthConfigured && (
                  <p className="text-sm text-text-tertiary">
                    Sign-in is not configured in this local preview.
                  </p>
                )}
              </>
            ) : ready ? (
              <button
                className={button}
                onClick={() => {
                  const url = safeHardwareCheckout(ready.url);
                  if (
                    url &&
                    boundary.current.mounted &&
                    boundary.current.generation === ready.generation &&
                    auth?.currentUser === user
                  )
                    navigateToHardwareCheckout(url);
                }}
              >
                Continue to checkout
              </button>
            ) : busy ? (
              <p role="status" className="text-sm text-text-tertiary">
                Preparing checkout...
              </p>
            ) : error && retryable ? (
              <button
                className={button}
                onClick={() => {
                  started.current = null;
                  void prepareCheckout();
                }}
              >
                Try again
              </button>
            ) : null}
          </div>
        )}
        {(error || Boolean(redirectSignInError)) && (
          <p role="alert" className="mt-4 text-sm text-text-tertiary">
            {error ?? 'Sign-in did not finish. Please try again.'}
          </p>
        )}
      </div>
    </main>
  );
}
