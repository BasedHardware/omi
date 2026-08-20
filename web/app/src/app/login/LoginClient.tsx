'use client';

import { useEffect, useState } from 'react';
import { useRouter } from '@tschk/moonshine-next/navigation';
import Image from '@tschk/moonshine-next/image';
import Link from '@tschk/moonshine-next/link';
import { motion } from 'framer-motion';
import { useAuth } from '@/components/auth/AuthProvider';
import { cn } from '@/lib/utils';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import { isFirebaseAuthConfigured } from '@/lib/firebase';

export function getAuthErrorMessage(
  error: unknown,
  provider: 'Google' | 'Apple',
): string {
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String(error.code)
      : '';
  if (code === 'auth/unauthorized-domain') {
    return 'This sign-in link is not enabled for this web address yet.';
  }
  if (code === 'auth/popup-blocked') {
    return 'Your browser blocked the sign-in window. Allow pop-ups and try again.';
  }
  if (code === 'auth/popup-closed-by-user') {
    return 'The sign-in window was closed before sign-in finished.';
  }
  if (code === 'auth/configuration-not-found') {
    return 'Sign-in is not configured in this local preview.';
  }
  return `Failed to sign in with ${provider}. Please try again.`;
}

const omiMarkDots = [
  { finalX: 0, finalY: -23, startX: -38, startY: -48 },
  { finalX: 16, finalY: -16, startX: 42, startY: -35 },
  { finalX: 23, finalY: 0, startX: 48, startY: 4 },
  { finalX: 16, finalY: 16, startX: 37, startY: 42 },
  { finalX: 0, finalY: 23, startX: 3, startY: 52 },
  { finalX: -16, finalY: 16, startX: -43, startY: 39 },
  { finalX: -23, finalY: 0, startX: -52, startY: -3 },
  { finalX: -16, finalY: -16, startX: -36, startY: -42 },
] as const;

export function LoginClient() {
  const { user, loading, signInWithGoogle, signInWithApple } = useAuth();
  const router = useRouter();
  const [isSigningIn, setIsSigningIn] = useState<'google' | 'apple' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const signInUnavailable = !isFirebaseAuthConfigured;
  const statusMessage =
    error ??
    (signInUnavailable ? 'Sign-in is not configured in this local preview.' : null);

  // Track page view
  useEffect(() => {
    MixpanelManager.pageView('Login');
  }, []);

  // Redirect to home if already logged in
  useEffect(() => {
    if (!loading && user) {
      router.push('/home');
    }
  }, [user, loading, router]);

  const handleGoogleSignIn = async () => {
    setIsSigningIn('google');
    setError(null);
    try {
      await signInWithGoogle();
      router.push('/home');
    } catch (err) {
      setError(getAuthErrorMessage(err, 'Google'));
      console.error(err);
    } finally {
      setIsSigningIn(null);
    }
  };

  const handleAppleSignIn = async () => {
    setIsSigningIn('apple');
    setError(null);
    try {
      await signInWithApple();
      router.push('/home');
    } catch (err) {
      setError(getAuthErrorMessage(err, 'Apple'));
      console.error(err);
    } finally {
      setIsSigningIn(null);
    }
  };

  // Show loading state while checking auth
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-primary">
        <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  // Don't show login if user is already logged in (will redirect)
  if (user) {
    return null;
  }

  return (
    <div className="relative min-h-[100svh] overflow-hidden bg-black">
      {/* Background Image with subtle floating animation */}
      <motion.div
        initial={{ opacity: 0, scale: 1.05 }}
        animate={{
          opacity: 1,
          scale: 1,
          y: [0, -8, 0],
        }}
        transition={{
          opacity: { duration: 1.2, ease: 'easeOut' },
          scale: { duration: 1.2, ease: 'easeOut' },
          y: {
            duration: 9,
            repeat: Infinity,
            ease: 'easeInOut',
            delay: 1.5,
          },
        }}
        className="absolute inset-0 z-0"
      >
        {/*
          The device's light sits at image fraction (0.4975, 0.4975) — the
          artwork's centre. The image is square, so a plain centred `cover` crop
          lands that light on the viewport's centre point at every size. The
          mark is pinned to the same point, which is how the ring stays around
          the light instead of only lining up at one window size.
        */}
        <Image
          src="/login-bg.png"
          alt="Omi Product"
          fill
          className="object-contain object-center sm:object-cover"
          priority
        />
        {/* Darker overlay for better contrast */}
        <div className="absolute inset-0 bg-black/70" />
      </motion.div>

      {/* Vignette effect - darkens edges */}
      <div
        className="absolute inset-0 z-10 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse at 50% 50%, transparent 0%, rgba(0, 0, 0, 0.4) 70%, rgba(0, 0, 0, 0.7) 100%)',
        }}
      />

      {/* Login Form (centered) */}
      <div className="relative z-20 flex min-h-[100svh] items-center justify-center px-5 py-8 sm:px-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
        >
          <div className="relative flex w-full max-w-xs flex-col items-center">
            {/* Headline */}
            <motion.h1
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 }}
              className="text-2xl font-display font-semibold text-text-primary mb-1"
            >
              Omi
            </motion.h1>

            {/* Tagline */}
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}
              className="text-text-tertiary text-sm mb-8"
            >
              thought to action
            </motion.p>

            {/*
              The mark is pinned to the viewport centre, not laid out in this
              column, because that is where the device's light falls under a
              centred `cover` crop. `fixed` + `-translate-1/2` keeps the ring
              around the light at any window size; laying it out in flow only
              ever lined the two up at one specific height. The spacer below
              holds the column's rhythm so the buttons do not move.
            */}
            {/*
              Positioning lives on this plain wrapper, not on the motion element
              below. Framer writes `transform` for the scale animation, which
              overrides Tailwind's `-translate-x-1/2 -translate-y-1/2` and left
              the ring offset by half its own box.
            */}
            <div className="fixed left-1/2 top-1/2 z-10 hidden -translate-x-1/2 -translate-y-1/2 sm:block">
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                whileHover={{ scale: 1.03 }}
                transition={{ duration: 0.3 }}
              >
                <div className="w-16 h-16 relative group" role="img" aria-label="Omi">
                  {/* Blue glow effect - outer */}
                  <div className="absolute inset-[-10px] rounded-full bg-blue-500/15 blur-xl group-hover:bg-blue-500/25 transition-all duration-500" />
                  {/* Purple glow effect - inner */}
                  <div className="absolute inset-0 rounded-full bg-white/10 blur-lg group-hover:bg-white/15 transition-all duration-500" />
                  {omiMarkDots.map((dot, index) => (
                    <motion.span
                      key={`omi-mark-dot-${index}`}
                      initial={{ opacity: 0, scale: 0.5, x: dot.startX, y: dot.startY }}
                      animate={{ opacity: 1, scale: 1, x: dot.finalX, y: dot.finalY }}
                      transition={{
                        duration: 0.85,
                        delay: 0.2 + index * 0.06,
                        ease: 'easeOut',
                      }}
                      style={{ marginLeft: -4, marginTop: -4 }}
                      className="absolute left-1/2 top-1/2 z-10 h-2 w-2 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.85)]"
                    />
                  ))}
                </div>
              </motion.div>
            </div>

            {/* Reserves the space the pinned mark used to occupy in flow. */}
            <div aria-hidden="true" className="mb-16 hidden h-16 w-16 sm:block" />

            {/* Auth buttons */}
            <motion.div
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 1.25, ease: 'easeOut' }}
              className="w-full space-y-2"
            >
              {/* Apple Sign In */}
              <button
                onClick={handleAppleSignIn}
                disabled={isSigningIn !== null || signInUnavailable}
                aria-label="Sign in with Apple"
                className={cn(
                  'flex h-12 w-full items-center justify-center gap-3 rounded-lg px-4',
                  'bg-black text-white font-medium border border-white/10',
                  'transition-all duration-150',
                  'hover:bg-gray-900',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary',
                  'disabled:cursor-not-allowed disabled:bg-black disabled:text-white disabled:opacity-100',
                )}
              >
                {isSigningIn === 'apple' ? (
                  <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                ) : (
                  <svg className="w-5 h-5" viewBox="0 0 24 24" fill="white">
                    <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
                  </svg>
                )}
                <span>
                  {isSigningIn === 'apple' ? 'Connecting...' : 'Continue with Apple'}
                </span>
              </button>

              {/* Google Sign In */}
              <button
                onClick={handleGoogleSignIn}
                disabled={isSigningIn !== null || signInUnavailable}
                aria-label="Sign in with Google"
                className={cn(
                  'flex h-12 w-full items-center justify-center gap-3 rounded-lg px-4',
                  'bg-white text-black font-medium',
                  'transition-all duration-150',
                  'hover:bg-gray-100',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary',
                  'disabled:cursor-not-allowed disabled:bg-white disabled:text-black disabled:opacity-100',
                )}
              >
                {isSigningIn === 'google' ? (
                  <div className="w-5 h-5 border-2 border-black/20 border-t-black rounded-full animate-spin" />
                ) : (
                  <svg className="w-5 h-5" viewBox="0 0 24 24">
                    <path
                      fill="#4285F4"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                    />
                    <path
                      fill="#EA4335"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                    />
                  </svg>
                )}
                <span>
                  {isSigningIn === 'google' ? 'Connecting...' : 'Continue with Google'}
                </span>
              </button>
            </motion.div>

            <div
              role="status"
              aria-live="polite"
              className="absolute inset-x-0 top-full mt-3 h-[72px] w-full"
            >
              {statusMessage && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="w-full rounded-lg border border-red-300/20 bg-red-500/10 px-3 py-2 text-center text-sm text-error"
                >
                  {statusMessage}
                </motion.p>
              )}
            </div>
          </div>
        </motion.div>
      </div>

      {/* Footer links - positioned at bottom */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.5 }}
        className="absolute bottom-3 left-0 right-0 z-30 flex justify-center gap-3 text-xs text-text-tertiary"
      >
        <a
          href="https://www.omi.me/"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-text-primary transition-colors"
        >
          About
        </a>
        <span>·</span>
        <a
          href="https://www.omi.me/pages/privacy"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-text-primary transition-colors"
        >
          Privacy
        </a>
        <span>·</span>
        <a
          href="https://help.omi.me/"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-text-primary transition-colors"
        >
          Help
        </a>
        <span>·</span>
        <Link href="/apps" className="hover:text-text-primary transition-colors">
          Apps
        </Link>
      </motion.div>
    </div>
  );
}
