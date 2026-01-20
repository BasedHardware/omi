'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Mic, Zap, X, Rocket } from 'lucide-react';
import { cn } from '@/lib/utils';

// Increment this version when adding new features
const WHATS_NEW_VERSION = 1;
const STORAGE_KEY = 'omi_whats_new_version';

interface Feature {
  icon: React.ReactNode;
  title: string;
  description: string;
}

// Update this list when you want to announce new features
const CURRENT_FEATURES: Feature[] = [
  {
    icon: <Mic className="w-4 h-4 text-purple-primary" />,
    title: 'Microphone Recording',
    description: 'Record conversations directly from your browser',
  },
  {
    icon: <Zap className="w-4 h-4 text-purple-primary" />,
    title: 'Performance Improvements',
    description: 'Faster loading times and smoother experience',
  },
  {
    icon: <Sparkles className="w-4 h-4 text-purple-primary" />,
    title: 'Enhanced UI',
    description: 'Refined interface with better responsiveness',
  },
];

export function WhatsNewModal() {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    // Check the last version the user has seen
    const lastSeenVersion = localStorage.getItem(STORAGE_KEY);
    const lastVersion = lastSeenVersion ? parseInt(lastSeenVersion, 10) : 0;

    // Show modal if there's a new version
    if (lastVersion < WHATS_NEW_VERSION) {
      // Small delay to let the page load first
      const timer = setTimeout(() => {
        setIsOpen(true);
      }, 800);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleClose = () => {
    localStorage.setItem(STORAGE_KEY, WHATS_NEW_VERSION.toString());
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
              'overflow-hidden relative'
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
                  <Rocket className="w-8 h-8 text-purple-primary" />
                </div>
                <h2 className="text-2xl font-semibold text-text-primary mb-2">
                  What&apos;s New
                </h2>
                <p className="text-text-tertiary">
                  Check out the latest updates
                </p>
              </div>
            </div>

            {/* Content */}
            <div className="px-6 pb-6 space-y-4">
              {/* Feature list */}
              <div className="space-y-3">
                {CURRENT_FEATURES.map((feature, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.1 + index * 0.1 }}
                    className="flex items-start gap-3 p-3 rounded-xl bg-bg-tertiary/50"
                  >
                    <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-purple-primary/10 flex items-center justify-center">
                      {feature.icon}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-text-primary">
                        {feature.title}
                      </p>
                      <p className="text-xs text-text-tertiary">
                        {feature.description}
                      </p>
                    </div>
                  </motion.div>
                ))}
              </div>

              {/* Action button */}
              <div className="pt-4">
                <button
                  onClick={handleClose}
                  className="block w-full py-3 px-4 rounded-xl bg-purple-primary text-white text-center font-medium hover:bg-purple-600 transition-colors"
                >
                  Got it!
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
