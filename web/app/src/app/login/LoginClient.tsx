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

  useEffect(() => {
    MixpanelManager.pageView('Login');
  }, []);

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

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-primary">
        <div className="w-12 h-12 border-3 border-brand/30 border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  if (user) return null;

  return (
    <div className="min-h-screen relative overflow-hidden bg-bg-primary">
      {/* Background image — matches landing hero */}
      <motion.div
        initial={{ opacity: 0, scale: 1.05 }}
        animate={{ opacity: 0.9, scale: 1 }}
        transition={{ duration: 2, ease: 'easeOut' }}
        className="absolute inset-0 z-0"
      >
        <Image
          src="/login-bg.png"
          alt=""
          fill
          className="object-cover object-center"
          priority
          sizes="100vw"
        />
        <div className="absolute inset-0 bg-black/40" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-bg-primary" />
      </motion.div>

      {/* Subtle brand glow — matches landing */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-brand/[0.03] rounded-full blur-[150px] z-0" />

      {/* Content */}
      <div className="relative z-10 min-h-screen flex flex-col items-center justify-end pb-[12vh] px-6">
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1], delay: 0.1 }}
          className="text-center max-w-md mx-auto"
        >
          {/* Heading — landing style with display + serif italic */}
          <h1 className="text-[clamp(2.5rem,6vw,4rem)] tracking-tight leading-[1.1] mb-4 text-white drop-shadow-[0_2px_30px_rgba(0,0,0,0.8)]">
            <span className="font-display font-semibold">Your AI</span>{' '}
            <span className="font-serif italic font-medium">companion</span>
          </h1>

          <p className="text-white/80 text-lg max-w-sm mx-auto leading-relaxed mb-10 drop-shadow-[0_1px_15px_rgba(0,0,0,0.7)]">
            Capture conversations, recall memories, and turn thoughts into action.
          </p>

          {/* Auth buttons — landing CTA style */}
          <div className="flex flex-col items-center gap-3 w-full max-w-xs mx-auto">
            <button
              onClick={handleAppleSignIn}
              disabled={isSigningIn !== null}
              className={cn(
                'w-full flex items-center justify-center gap-3 px-7 py-3.5 rounded-full',
                'bg-white text-black font-medium text-sm',
                'hover:bg-white/90 transition-all',
                'shadow-lg shadow-black/20',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {isSigningIn === 'apple' ? (
                <div className="w-4 h-4 border-2 border-black/20 border-t-black rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="black">
                  <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
                </svg>
              )}
              {isSigningIn === 'apple' ? 'Connecting...' : 'Continue with Apple'}
            </button>

            <button
              onClick={handleGoogleSignIn}
              disabled={isSigningIn !== null}
              className={cn(
                'w-full flex items-center justify-center gap-3 px-7 py-3.5 rounded-full',
                'text-white font-medium text-sm',
                'border border-white/40 bg-white/15 backdrop-blur-sm',
                'hover:bg-white/25 transition-all',
                'shadow-lg shadow-black/20',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {isSigningIn === 'google' ? (
                <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4" viewBox="0 0 24 24">
                  <path fill="#fff" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path fill="#fff" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#fff" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                  <path fill="#fff" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                </svg>
              )}
              {isSigningIn === 'google' ? 'Connecting...' : 'Continue with Google'}
            </button>
          </div>

          {/* Error */}
          {error && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-4 text-destructive text-sm"
            >
              {error}
            </motion.p>
          )}

          {/* App links */}
          <p className="mt-8 text-sm text-white/50">
            New to Nooto?{' '}
            <a href="https://apps.apple.com/us/app/friend-ai-wearable/id6502156163" target="_blank" rel="noopener noreferrer" className="text-white/70 hover:text-white transition-colors underline underline-offset-2 decoration-white/30">
              iOS
            </a>
            {' · '}
            <a href="https://play.google.com/store/apps/details?id=com.friend.ios" target="_blank" rel="noopener noreferrer" className="text-white/70 hover:text-white transition-colors underline underline-offset-2 decoration-white/30">
              Android
            </a>
          </p>
        </motion.div>

        {/* Device / Logo — matches landing hero device */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1.2, delay: 0.4 }}
          className="absolute top-[15vh] left-1/2 -translate-x-1/2"
        >
          <div className="relative w-32 h-32">
            <div className="absolute inset-[-50%] rounded-full bg-brand/[0.06] blur-[80px] pointer-events-none" />
            <div className="absolute -top-12 left-1/2 -translate-x-1/2 w-px h-12 bg-gradient-to-t from-white/15 to-transparent" />
            <div className="relative w-full h-full rounded-full bg-gradient-to-b from-[#2a2a2a] to-[#1a1a1a] border border-white/10 flex items-center justify-center shadow-[0_0_60px_rgba(0,0,0,0.5)]">
              <div className="w-[75%] h-[75%] rounded-full bg-gradient-to-b from-[#333] to-[#222] border border-white/[0.08] flex items-center justify-center">
                <div className="w-[55%] h-[55%] rounded-full bg-gradient-to-br from-brand/40 to-brand/15 border border-brand/25 shadow-[0_0_40px_rgba(59,130,246,0.2)]" />
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Footer */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.8 }}
        className="absolute bottom-4 left-0 right-0 z-20 flex justify-center gap-4 text-xs text-white/30"
      >
        <a href="https://www.omi.me/" target="_blank" rel="noopener noreferrer" className="hover:text-white/60 transition-colors">About</a>
        <span>·</span>
        <a href="https://www.omi.me/pages/privacy" target="_blank" rel="noopener noreferrer" className="hover:text-white/60 transition-colors">Privacy</a>
        <span>·</span>
        <a href="https://help.omi.me/" target="_blank" rel="noopener noreferrer" className="hover:text-white/60 transition-colors">Help</a>
      </motion.div>
    </div>
  );
}
