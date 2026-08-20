'use client';

import { useState, useEffect } from 'react';
import { X, Sparkles, LogIn } from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';

const STORAGE_KEY = 'omi-promo-dismissed';

export function PromoCard() {
  const [isVisible, setIsVisible] = useState(false);
  const [isAnimatingOut, setIsAnimatingOut] = useState(false);
  const { openLoginPanel } = useAuth();

  useEffect(() => {
    // Check if already dismissed
    const dismissed = localStorage.getItem(STORAGE_KEY);
    if (!dismissed) {
      // Delay showing to let the page load first
      const timer = setTimeout(() => setIsVisible(true), 1000);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleDismiss = () => {
    setIsAnimatingOut(true);
    localStorage.setItem(STORAGE_KEY, 'true');
    setTimeout(() => setIsVisible(false), 300);
  };

  const handleSignIn = () => {
    openLoginPanel();
    handleDismiss();
  };

  if (!isVisible) return null;

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 w-80 overflow-hidden rounded-2xl border border-white/10 bg-white/5 p-5 shadow-2xl backdrop-blur-xl transition-all duration-300 ${
        isAnimatingOut
          ? 'translate-y-4 opacity-0'
          : 'translate-y-0 opacity-100 animate-in slide-in-from-bottom-4'
      }`}
    >
      {/* Gradient accent bar */}
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-white/70 via-white/30 to-transparent" />

      {/* Dismiss button */}
      <button
        onClick={handleDismiss}
        className="absolute right-3 top-3 rounded-full p-1 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
        aria-label="Dismiss"
      >
        <X className="h-4 w-4" />
      </button>

      {/* Content */}
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/[0.10]">
          <Sparkles className="h-5 w-5 text-text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-white">Try the New Web Experience</h3>
          <p className="mt-1 text-sm text-gray-400">
            Access your conversations, memories, and apps from any browser.
          </p>
        </div>
      </div>

      {/* CTA */}
      <button
        onClick={handleSignIn}
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-black transition-all hover:bg-white/90 hover:shadow-lg hover:shadow-white/20"
      >
        <LogIn className="h-4 w-4" />
        Sign In
      </button>

      {/* Decorative glow */}
      <div className="pointer-events-none absolute -bottom-20 -right-20 h-40 w-40 rounded-full bg-white/10 blur-3xl" />
      <div className="pointer-events-none absolute -left-10 -top-10 h-32 w-32 rounded-full bg-white/[0.06] blur-3xl" />
    </div>
  );
}
