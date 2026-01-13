'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, MessageSquare, Bug, X, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import confetti from 'canvas-confetti';

// Discord icon component
function DiscordIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
    </svg>
  );
}

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
    // Fire full-page confetti celebration
    const duration = 2000;
    const end = Date.now() + duration;

    const frame = () => {
      // Left side
      confetti({
        particleCount: 3,
        angle: 60,
        spread: 55,
        origin: { x: 0, y: 0.6 },
        colors: ['#8B5CF6', '#A78BFA', '#C4B5FD', '#ffffff']
      });
      // Right side
      confetti({
        particleCount: 3,
        angle: 120,
        spread: 55,
        origin: { x: 1, y: 0.6 },
        colors: ['#8B5CF6', '#A78BFA', '#C4B5FD', '#ffffff']
      });

      if (Date.now() < end) {
        requestAnimationFrame(frame);
      }
    };

    frame();
    localStorage.setItem(STORAGE_KEY, 'true');
    setIsOpen(false);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/50 p-4"
          onClick={handleClose}
        >
          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            onClick={(e) => e.stopPropagation()}
            className={cn(
              'w-full max-w-md bg-bg-secondary rounded-2xl',
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

              {/* Feedback links */}
              <div className="pt-2 space-y-2">
                <p className="text-xs text-text-quaternary">Share your feedback:</p>
                <div className="flex items-center gap-4">
                  <a
                    href="https://feedback.omi.me"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-sm text-text-tertiary hover:text-purple-primary transition-colors"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>feedback.omi.me</span>
                  </a>
                  <a
                    href="https://discord.gg/omidotme"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-sm text-text-tertiary hover:text-purple-primary transition-colors"
                  >
                    <DiscordIcon className="w-3.5 h-3.5" />
                    <span>Discord</span>
                  </a>
                </div>
              </div>

              {/* Action button */}
              <div className="pt-4">
                <button
                  onClick={handleClose}
                  className="block w-full py-3 px-4 rounded-xl bg-purple-primary text-white text-center font-medium hover:bg-purple-600 transition-colors"
                >
                  Got it, let&apos;s go!
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
