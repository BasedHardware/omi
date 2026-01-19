'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { motion } from 'framer-motion';
import { useAuth } from '@/components/auth/AuthProvider';
import { cn } from '@/lib/utils';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

export function LoginClient() {
  const { user, loading, signInWithGoogle, signInWithApple } = useAuth();
  const router = useRouter();
  const [isSigningIn, setIsSigningIn] = useState<'google' | 'apple' | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Track page view
  useEffect(() => {
    MixpanelManager.pageView('Login');
  }, []);

  // Redirect to conversations if already logged in
  useEffect(() => {
    if (!loading && user) {
      router.push('/conversations');
    }
  }, [user, loading, router]);

  const handleGoogleSignIn = async () => {
    setIsSigningIn('google');
    setError(null);
    try {
      await signInWithGoogle();
      router.push('/conversations');
    } catch (err) {
      setError('Failed to sign in with Google. Please try again.');
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
      router.push('/conversations');
    } catch (err) {
      setError('Failed to sign in with Apple. Please try again.');
      console.error(err);
    } finally {
      setIsSigningIn(null);
    }
  };

  // Show loading state while checking auth
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-primary">
        <div className="w-16 h-16 border-4 border-purple-primary/30 border-t-purple-primary rounded-full animate-spin" />
      </div>
    );
  }

  // Don't show login if user is already logged in (will redirect)
  if (user) {
    return null;
  }

  return (
    <div className="min-h-screen relative overflow-hidden bg-black">
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
            delay: 1.5
          }
        }}
        className="absolute inset-0 z-0"
      >
        <Image
          src="/login-bg.png"
          alt="Omi Product"
          fill
          className="object-cover"
          priority
        />
        {/* Darker overlay for better contrast */}
        <div className="absolute inset-0 bg-black/55" />
      </motion.div>

      {/* Vignette effect - darkens edges */}
      <div
        className="absolute inset-0 z-10 pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at 50% 50%, transparent 0%, rgba(0, 0, 0, 0.4) 70%, rgba(0, 0, 0, 0.7) 100%)',
        }}
      />

      {/* Login Form (centered) */}
      <div className="relative z-20 min-h-screen flex items-center justify-center px-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
        >
          <div className="w-full max-w-sm flex flex-col items-center">
          {/* Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 }}
            className="text-3xl font-display font-semibold text-text-primary mb-2"
          >
            Omi
          </motion.h1>

          {/* Tagline */}
          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.3 }}
            className="text-text-tertiary text-lg mb-28"
          >
            thought to action
          </motion.p>

          {/* Logo with glow and hover animation */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            whileHover={{ scale: 1.05, rotate: 10 }}
            transition={{ duration: 0.3 }}
            className="mb-14"
          >
            <div className="w-28 h-28 relative group">
              {/* Blue glow effect - outer */}
              <div className="absolute inset-[-20px] rounded-full bg-blue-500/30 blur-2xl group-hover:bg-blue-500/50 transition-all duration-500" />
              {/* Purple glow effect - inner */}
              <div className="absolute inset-0 rounded-full bg-purple-primary/20 blur-xl group-hover:bg-purple-primary/40 transition-all duration-500" />
              <Image
                src="/logo.png"
                alt="Omi"
                fill
                className="object-contain relative z-10 drop-shadow-[0_0_25px_rgba(59,130,246,0.6)] group-hover:drop-shadow-[0_0_35px_rgba(59,130,246,0.8)] transition-all duration-300"
                priority
              />
            </div>
          </motion.div>

          {/* Auth buttons */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.2 }}
            className="w-full space-y-4"
          >
            {/* Apple Sign In */}
            <button
              onClick={handleAppleSignIn}
              disabled={isSigningIn !== null}
              aria-label="Sign in with Apple"
              className={cn(
                'w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl',
                'bg-black text-white font-medium border border-white/10',
                'transition-all duration-150',
                'hover:bg-gray-900 hover:scale-[1.02]',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary',
                'disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100'
              )}
            >
              {isSigningIn === 'apple' ? (
                <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
              ) : (
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="white">
                  <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
                </svg>
              )}
              <span>{isSigningIn === 'apple' ? 'Connecting...' : 'Continue with Apple'}</span>
            </button>

            {/* Google Sign In */}
            <button
              onClick={handleGoogleSignIn}
              disabled={isSigningIn !== null}
              aria-label="Sign in with Google"
              className={cn(
                'w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl',
                'bg-white text-black font-medium',
                'transition-all duration-150',
                'hover:bg-gray-100 hover:scale-[1.02]',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary',
                'disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100'
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
              <span>{isSigningIn === 'google' ? 'Connecting...' : 'Continue with Google'}</span>
            </button>
          </motion.div>

          {/* App download message - for users without accounts */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3, delay: 0.4 }}
            className="mt-6 text-center"
          >
            <p className="text-sm text-text-tertiary">
              New to Omi?{' '}
              <a
                href="https://apps.apple.com/us/app/friend-ai-wearable/id6502156163"
                target="_blank"
                rel="noopener noreferrer"
                className="text-text-secondary hover:text-text-primary transition-colors underline decoration-text-secondary/40 hover:decoration-text-primary/60"
              >
                iOS
              </a>
              {' · '}
              <a
                href="https://play.google.com/store/apps/details?id=com.friend.ios"
                target="_blank"
                rel="noopener noreferrer"
                className="text-text-secondary hover:text-text-primary transition-colors underline decoration-text-secondary/40 hover:decoration-text-primary/60"
              >
                Android
              </a>
            </p>
          </motion.div>

          {/* Error message */}
          {error && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-4 text-error text-sm text-center"
            >
              {error}
            </motion.p>
          )}
          </div>
        </motion.div>
      </div>

      {/* Footer links - positioned at bottom */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.5 }}
        className="absolute bottom-4 left-0 right-0 z-30 flex justify-center gap-4 text-sm text-text-tertiary"
      >
        <a href="https://www.omi.me/" target="_blank" rel="noopener noreferrer" className="hover:text-text-primary transition-colors">
          About
        </a>
        <span>·</span>
        <a href="https://www.omi.me/pages/privacy" target="_blank" rel="noopener noreferrer" className="hover:text-text-primary transition-colors">
          Privacy
        </a>
        <span>·</span>
        <a href="https://help.omi.me/" target="_blank" rel="noopener noreferrer" className="hover:text-text-primary transition-colors">
          Help
        </a>
        <span>·</span>
        <a href="/apps" className="hover:text-text-primary transition-colors">
          Apps
        </a>
      </motion.div>
    </div>
  );
}
