'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, MessageSquare, Bug, X } from 'lucide-react';
import { cn } from '@/lib/utils';

const STORAGE_KEY = 'omi_beta_welcome_seen';

export function BetaWelcomeModal() {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    // Check if user has already seen the welcome modal
    const hasSeenWelcome = localStorage.getItem(STORAGE_KEY);
    if (!hasSeenWelcome) {
      // Small delay to let the page load first
      const timer = setTimeout(() => {
        setIsOpen(true);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleClose = () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    setIsOpen(false);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={handleClose}
            className="fixed inset-0 bg-black/50 z-[10000]"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className={cn(
              'fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[10000]',
              'w-full max-w-md mx-4 bg-bg-secondary rounded-2xl',
              'shadow-xl border border-bg-tertiary',
              'overflow-hidden'
            )}
          >
            {/* Close button */}
            <button
              onClick={handleClose}
              className="absolute top-4 right-4 p-2 rounded-lg hover:bg-bg-tertiary transition-colors z-10"
            >
              <X className="w-5 h-5 text-text-tertiary" />
            </button>

            {/* Header with gradient */}
            <div className="relative px-6 pt-8 pb-6 text-center">
              <div className="absolute inset-0 bg-gradient-to-b from-purple-primary/10 to-transparent" />
              <div className="relative">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-purple-primary/20 mb-4">
                  <Sparkles className="w-8 h-8 text-purple-primary" />
                </div>
                <h2 className="text-2xl font-semibold text-text-primary mb-2">
                  Welcome to Omi Web Beta
                </h2>
                <p className="text-text-tertiary">
                  Thanks for being an early adopter!
                </p>
              </div>
            </div>

            {/* Content */}
            <div className="px-6 pb-6 space-y-4">
              {/* Feature list */}
              <div className="space-y-3">
                <div className="flex items-start gap-3 p-3 rounded-xl bg-bg-tertiary/50">
                  <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-purple-primary/10 flex items-center justify-center">
                    <Sparkles className="w-4 h-4 text-purple-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-text-primary">Early Access Features</p>
                    <p className="text-xs text-text-tertiary">Features may change as we improve the experience</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-xl bg-bg-tertiary/50">
                  <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-purple-primary/10 flex items-center justify-center">
                    <Bug className="w-4 h-4 text-purple-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-text-primary">Error Tracking</p>
                    <p className="text-xs text-text-tertiary">We capture errors to improve stability</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 p-3 rounded-xl bg-bg-tertiary/50">
                  <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-purple-primary/10 flex items-center justify-center">
                    <MessageSquare className="w-4 h-4 text-purple-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-text-primary">Your Feedback Matters</p>
                    <p className="text-xs text-text-tertiary">Help us build the best experience possible</p>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="pt-2 space-y-3">
                <a
                  href="https://feedback.omi.me"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block w-full py-3 px-4 rounded-xl bg-purple-primary text-white text-center font-medium hover:bg-purple-600 transition-colors"
                >
                  Share Feedback
                </a>
                <button
                  onClick={handleClose}
                  className="block w-full py-3 px-4 rounded-xl bg-bg-tertiary text-text-primary text-center font-medium hover:bg-bg-quaternary transition-colors"
                >
                  Got it, let&apos;s go!
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
