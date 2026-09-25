'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useAuth } from './AuthProvider';
import { cn } from '@/lib/utils';
import Image from '@tschk/moonshine-next/image';
import { useRouter } from '@tschk/moonshine-next/navigation';

interface LoginPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export function LoginPanel({ isOpen, onClose }: LoginPanelProps) {
  const { signInWithGoogle, signInWithApple } = useAuth();
  const [isLoading, setIsLoading] = useState<'google' | 'apple' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const handleGoogleSignIn = async () => {
    setIsLoading('google');
    setError(null);
    try {
      await signInWithGoogle();
      onClose();
      router.push('/home');
    } catch (err) {
      console.error('Google sign-in failed:', err);
      setError('Failed to sign in with Google. Please try again.');
    } finally {
      setIsLoading(null);
    }
  };

  const handleAppleSignIn = async () => {
    setIsLoading('apple');
    setError(null);
    try {
      await signInWithApple();
      onClose();
      router.push('/home');
    } catch (err) {
      console.error('Apple sign-in failed:', err);
      setError('Failed to sign in with Apple. Please try again.');
    } finally {
      setIsLoading(null);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop with blur */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Panel - slides in from right */}
          <motion.div
            initial={{ x: '100%', opacity: 0.8 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0.8 }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className={cn(
              'fixed right-0 top-0 z-50 h-full',
              'w-full sm:w-[420px]',
              'border-l border-white/10 bg-[#0B0F17]',
              'flex flex-col shadow-2xl',
            )}
          >
            {/* Subtle glow at top */}
            <div className="absolute left-0 right-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />

            {/* Close button */}
            <div className="absolute right-4 top-4 z-10">
              <button
                onClick={onClose}
                className="rounded-lg bg-white/5 p-2 transition-colors hover:bg-white/10"
                aria-label="Close"
              >
                <X className="h-5 w-5 text-gray-400" />
              </button>
            </div>

            {/* Content */}
            <div className="flex flex-1 flex-col items-center justify-center px-8 py-12">
              <div className="w-full max-w-sm space-y-8">
                {/* Logo and heading */}
                <div className="text-center">
                  <div className="mb-6 flex justify-center">
                    <Image
                      src="/omi-white.webp"
                      alt="Omi"
                      width={120}
                      height={48}
                      className="h-12 w-auto"
                    />
                  </div>
                  <h2 className="mb-2 text-2xl font-semibold text-white">Welcome back</h2>
                  <p className="text-sm text-gray-400">
                    Sign in to access your conversations, memories, and apps
                  </p>
                </div>

                {/* Error message */}
                {error && (
                  <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-3">
                    <p className="text-center text-sm text-red-400">{error}</p>
                  </div>
                )}

                {/* Sign in buttons */}
                <div className="space-y-3">
                  <button
                    onClick={handleGoogleSignIn}
                    disabled={isLoading !== null}
                    className={cn(
                      'flex w-full items-center justify-center gap-3 rounded-xl px-4 py-3.5',
                      'bg-white font-medium text-gray-900',
                      'transition-all hover:bg-gray-100',
                      'disabled:cursor-not-allowed disabled:opacity-50',
                      'shadow-lg shadow-white/5',
                    )}
                  >
                    {isLoading === 'google' ? (
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
                    ) : (
                      <svg className="h-5 w-5" viewBox="0 0 24 24">
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
                    Continue with Google
                  </button>

                  <button
                    onClick={handleAppleSignIn}
                    disabled={isLoading !== null}
                    className={cn(
                      'flex w-full items-center justify-center gap-3 rounded-xl px-4 py-3.5',
                      'border border-white/10 bg-white/5 font-medium text-white',
                      'transition-all hover:border-white/20 hover:bg-white/10',
                      'disabled:cursor-not-allowed disabled:opacity-50',
                    )}
                  >
                    {isLoading === 'apple' ? (
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
                    ) : (
                      <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09l.01-.01zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z" />
                      </svg>
                    )}
                    Continue with Apple
                  </button>
                </div>

                {/* Divider */}
                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-white/10"></div>
                  </div>
                  <div className="relative flex justify-center text-xs">
                    <span className="bg-[#0B0F17] px-3 text-gray-500">
                      Secure sign-in powered by Firebase
                    </span>
                  </div>
                </div>

                {/* Terms */}
                <p className="text-center text-xs leading-relaxed text-gray-500">
                  By signing in, you agree to our{' '}
                  <a
                    href="https://www.omi.me/pages/terms"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-text-primary transition-colors hover:text-text-secondary"
                  >
                    Terms of Service
                  </a>{' '}
                  and{' '}
                  <a
                    href="https://www.omi.me/pages/privacy"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-text-primary transition-colors hover:text-text-secondary"
                  >
                    Privacy Policy
                  </a>
                </p>
              </div>
            </div>

            {/* Bottom gradient accent */}
            <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-white/[0.05] to-transparent" />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
