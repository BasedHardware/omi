'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useAuth } from './AuthProvider';
import { cn } from '@/lib/utils';
import Image from 'next/image';
import { useRouter } from 'next/navigation';

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
      router.push('/conversations');
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
      router.push('/conversations');
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
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
            onClick={onClose}
          />

          {/* Panel - slides in from right */}
          <motion.div
            initial={{ x: '100%', opacity: 0.8 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0.8 }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className={cn(
              'fixed right-0 top-0 h-full z-50',
              'w-full sm:w-[420px]',
              'bg-[#0B0F17] border-l border-white/10',
              'flex flex-col shadow-2xl'
            )}
          >
            {/* Subtle purple glow at top */}
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-purple-primary/50 to-transparent" />

            {/* Close button */}
            <div className="absolute top-4 right-4 z-10">
              <button
                onClick={onClose}
                className="p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
                aria-label="Close"
              >
                <X className="w-5 h-5 text-gray-400" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 flex flex-col items-center justify-center px-8 py-12">
              <div className="w-full max-w-sm space-y-8">
                {/* Logo and heading */}
                <div className="text-center">
                  <div className="flex justify-center mb-6">
                    <Image
                      src="/omi-white.webp"
                      alt="Omi"
                      width={120}
                      height={48}
                      className="h-12 w-auto"
                    />
                  </div>
                  <h2 className="text-2xl font-semibold text-white mb-2">
                    Welcome back
                  </h2>
                  <p className="text-gray-400 text-sm">
                    Sign in to access your conversations, memories, and apps
                  </p>
                </div>

                {/* Error message */}
                {error && (
                  <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20">
                    <p className="text-sm text-red-400 text-center">{error}</p>
                  </div>
                )}

                {/* Sign in buttons */}
                <div className="space-y-3">
                  <button
                    onClick={handleGoogleSignIn}
                    disabled={isLoading !== null}
                    className={cn(
                      'w-full flex items-center justify-center gap-3 px-4 py-3.5 rounded-xl',
                      'bg-white text-gray-900 font-medium',
                      'hover:bg-gray-100 transition-all',
                      'disabled:opacity-50 disabled:cursor-not-allowed',
                      'shadow-lg shadow-white/5'
                    )}
                  >
                    {isLoading === 'google' ? (
                      <div className="w-5 h-5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
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
                    Continue with Google
                  </button>

                  <button
                    onClick={handleAppleSignIn}
                    disabled={isLoading !== null}
                    className={cn(
                      'w-full flex items-center justify-center gap-3 px-4 py-3.5 rounded-xl',
                      'bg-white/5 text-white font-medium border border-white/10',
                      'hover:bg-white/10 hover:border-white/20 transition-all',
                      'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                  >
                    {isLoading === 'apple' ? (
                      <div className="w-5 h-5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
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
                    <span className="px-3 bg-[#0B0F17] text-gray-500">
                      Secure sign-in powered by Firebase
                    </span>
                  </div>
                </div>

                {/* Terms */}
                <p className="text-xs text-gray-500 text-center leading-relaxed">
                  By signing in, you agree to our{' '}
                  <a
                    href="https://www.omi.me/pages/terms"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-purple-primary hover:text-purple-secondary transition-colors"
                  >
                    Terms of Service
                  </a>{' '}
                  and{' '}
                  <a
                    href="https://www.omi.me/pages/privacy"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-purple-primary hover:text-purple-secondary transition-colors"
                  >
                    Privacy Policy
                  </a>
                </p>
              </div>
            </div>

            {/* Bottom gradient accent */}
            <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-purple-primary/5 to-transparent pointer-events-none" />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
