'use client';

import { useEffect } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { Sparkles, Mic, Zap, X, Rocket } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Feature {
  icon: React.ReactNode;
  title: string;
  description: string;
}

// Update this list when you want to announce new features
const CURRENT_FEATURES: Feature[] = [
  {
    icon: <Mic className="w-4 h-4 text-text-primary" />,
    title: 'Microphone Recording',
    description: 'Record conversations directly from your browser',
  },
  {
    icon: <Zap className="w-4 h-4 text-text-primary" />,
    title: 'Performance Improvements',
    description: 'Faster loading times and smoother experience',
  },
  {
    icon: <Sparkles className="w-4 h-4 text-text-primary" />,
    title: 'Enhanced UI',
    description: 'Refined interface with better responsiveness',
  },
];

interface WhatsNewModalProps {
  onDismiss: () => void;
}

export function WhatsNewModal({ onDismiss }: WhatsNewModalProps) {
  const reduceMotion = useReducedMotion();

  const handleClose = () => {
    onDismiss();
  };

  // Escape is the third way out, alongside the button and the backdrop. Every
  // path runs the same `onDismiss`, which is what writes the seen flag.
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onDismiss();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onDismiss]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: reduceMotion ? 0.16 : 0.2 }}
      className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/50 p-4"
      onClick={handleClose}
    >
      {/* Modal. The enter/exit offsets are `y` and `scale` numbers, not a
          `transform` string: `transform: 'none'` is interpolated as an
          all-zero matrix, which collapsed this dialog to 0×0 behind a
          screen-filling backdrop. The height cap keeps the action reachable on
          a phone. */}
      <motion.div
        initial={{
          opacity: 0,
          y: reduceMotion ? 0 : 20,
          scale: reduceMotion ? 1 : 0.95,
        }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{
          opacity: 0,
          y: reduceMotion ? 0 : 12,
          scale: reduceMotion ? 1 : 0.97,
        }}
        transition={{ duration: reduceMotion ? 0.16 : 0.22, ease: [0.23, 1, 0.32, 1] }}
        onClick={(e) => e.stopPropagation()}
        className={cn(
          'relative w-full max-w-md bg-bg-secondary rounded-2xl',
          'shadow-xl border border-bg-tertiary',
          'max-h-[calc(100dvh-2rem)] overflow-y-auto',
        )}
      >
        {/* Close button */}
        <button
          onClick={handleClose}
          aria-label="Close"
          className="absolute top-3 right-3 z-10 rounded-lg p-2 text-text-tertiary transition-colors hover:bg-bg-tertiary hover:text-text-primary"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header with gradient */}
        <div className="relative px-6 pt-8 pb-6 text-center">
          <div className="absolute inset-0 bg-gradient-to-b from-white/[0.06] to-transparent" />
          <div className="relative">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white/[0.14] mb-4">
              <Rocket className="w-8 h-8 text-text-primary" />
            </div>
            <h2 className="text-2xl font-semibold text-text-primary mb-2">
              What&apos;s New
            </h2>
            <p className="text-text-tertiary">Check out the latest updates</p>
          </div>
        </div>

        {/* Content */}
        <div className="px-6 pb-6 space-y-4">
          {/* Feature list */}
          <div className="space-y-3">
            {CURRENT_FEATURES.map((feature, index) => (
              <motion.div
                key={index}
                initial={{
                  opacity: 0,
                  x: reduceMotion ? 0 : -10,
                }}
                animate={{ opacity: 1, x: 0 }}
                transition={{
                  duration: reduceMotion ? 0.16 : 0.2,
                  delay: reduceMotion ? 0 : 0.06 + index * 0.05,
                  ease: [0.23, 1, 0.32, 1],
                }}
                className="flex items-start gap-3 p-3 rounded-xl bg-bg-tertiary/50"
              >
                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-white/[0.08] flex items-center justify-center">
                  {feature.icon}
                </div>
                <div>
                  <p className="text-sm font-medium text-text-primary">{feature.title}</p>
                  <p className="text-xs text-text-tertiary">{feature.description}</p>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Action button */}
          <div className="pt-4">
            <button
              onClick={handleClose}
              className="block w-full py-3 px-4 rounded-xl bg-text-primary text-bg-primary text-center font-medium hover:bg-text-primary/90 transition-colors"
            >
              Got it!
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
