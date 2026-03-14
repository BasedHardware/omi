'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { getStoredKeyHash } from '@/src/lib/e2ee';
import dynamic from 'next/dynamic';

const E2eeUnlock = dynamic(() => import('@/src/components/shared/e2ee-unlock'), { ssr: false });

interface E2eeContextValue {
  isLocked: boolean;
  keyHash: string | null;
  unlock: () => void;
  handleApiError: (status: number) => void;
}

const E2eeContext = createContext<E2eeContextValue>({
  isLocked: false,
  keyHash: null,
  unlock: () => {},
  handleApiError: () => {},
});

export function useE2ee() {
  return useContext(E2eeContext);
}

export function E2eeProvider({ children }: { children: ReactNode }) {
  const [keyHash, setKeyHash] = useState<string | null>(null);
  const [showDialog, setShowDialog] = useState(false);
  const [needsUnlock, setNeedsUnlock] = useState(false);

  useEffect(() => {
    const hash = getStoredKeyHash();
    setKeyHash(hash);
    setNeedsUnlock(false);
  }, []);

  const unlock = useCallback(() => {
    setShowDialog(true);
  }, []);

  const handleApiError = useCallback((status: number) => {
    if (status === 403) {
      setNeedsUnlock(true);
      setShowDialog(true);
    }
  }, []);

  const handleUnlocked = useCallback(() => {
    const hash = getStoredKeyHash();
    setKeyHash(hash);
    setNeedsUnlock(false);
    setShowDialog(false);
  }, []);

  const handleClose = useCallback(() => {
    setShowDialog(false);
  }, []);

  const isLocked = needsUnlock || (keyHash === null && needsUnlock);

  return (
    <E2eeContext.Provider value={{ isLocked, keyHash, unlock, handleApiError }}>
      {children}
      {showDialog && <E2eeUnlock onUnlocked={handleUnlocked} onClose={handleClose} />}
    </E2eeContext.Provider>
  );
}
