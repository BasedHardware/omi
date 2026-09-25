'use client';

import { useEffect, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { BetaWelcomeModal } from '@/components/ui/BetaWelcomeModal';
import { WhatsNewModal } from '@/components/ui/WhatsNewModal';

// Increment this version when adding new features
const WHATS_NEW_VERSION = 1;
const BETA_WELCOME_STORAGE_KEY = 'omi_beta_welcome_seen';
const WHATS_NEW_STORAGE_KEY = 'omi_whats_new_version';

type StartupModal = 'beta-welcome' | 'whats-new' | null;

export function StartupModals() {
  const [activeModal, setActiveModal] = useState<StartupModal>(null);
  const [whatsNewPending, setWhatsNewPending] = useState(false);

  useEffect(() => {
    // Check if user has already seen the welcome modal
    const hasSeenWelcome = localStorage.getItem(BETA_WELCOME_STORAGE_KEY);
    // Check the last version the user has seen
    const lastSeenVersion = localStorage.getItem(WHATS_NEW_STORAGE_KEY);
    const lastVersion = lastSeenVersion ? parseInt(lastSeenVersion, 10) : 0;
    const shouldShowWhatsNew = lastVersion < WHATS_NEW_VERSION;

    setWhatsNewPending(shouldShowWhatsNew);

    if (!hasSeenWelcome) {
      // Small delay to let the page load first
      const timer = setTimeout(() => setActiveModal('beta-welcome'), 500);
      return () => clearTimeout(timer);
    }

    // Show modal if there's a new version
    if (shouldShowWhatsNew) {
      // Small delay to let the page load first
      const timer = setTimeout(() => setActiveModal('whats-new'), 800);
      return () => clearTimeout(timer);
    }
  }, []);

  const dismissBetaWelcome = () => {
    localStorage.setItem(BETA_WELCOME_STORAGE_KEY, 'true');
    setActiveModal(whatsNewPending ? 'whats-new' : null);
  };

  const dismissWhatsNew = () => {
    localStorage.setItem(WHATS_NEW_STORAGE_KEY, WHATS_NEW_VERSION.toString());
    setActiveModal(null);
  };

  return (
    <AnimatePresence mode="wait">
      {activeModal === 'beta-welcome' && (
        <BetaWelcomeModal key="beta-welcome" onDismiss={dismissBetaWelcome} />
      )}
      {activeModal === 'whats-new' && (
        <WhatsNewModal key="whats-new" onDismiss={dismissWhatsNew} />
      )}
    </AnimatePresence>
  );
}
