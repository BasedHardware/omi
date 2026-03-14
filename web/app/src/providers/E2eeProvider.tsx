'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { getStoredKeyHash } from '@/lib/e2ee';
import E2eeUnlock from '@/components/shared/E2eeUnlock';

interface E2eeContextType {
  isE2eeRequired: boolean;
  isUnlocked: boolean;
  keyHash: string | null;
  showUnlock: () => void;
  handleApiError: (status: number, body?: string) => boolean;
}

const E2eeContext = createContext<E2eeContextType>({
  isE2eeRequired: false,
  isUnlocked: false,
  keyHash: null,
  showUnlock: () => {},
  handleApiError: () => false,
});

export function useE2ee() {
  return useContext(E2eeContext);
}

export function E2eeProvider({ children }: { children: ReactNode }) {
  const [isE2eeRequired, setIsE2eeRequired] = useState(false);
  const [isUnlocked, setIsUnlocked] = useState(false);
  const [keyHash, setKeyHash] = useState<string | null>(null);
  const [showDialog, setShowDialog] = useState(false);

  useEffect(() => {
    const hash = getStoredKeyHash();
    if (hash) {
      setIsUnlocked(true);
      setKeyHash(hash);
    }
  }, []);

  useEffect(() => {
    const handler = () => {
      setIsE2eeRequired(true);
      setShowDialog(true);
    };
    window.addEventListener('e2ee-required', handler);
    return () => window.removeEventListener('e2ee-required', handler);
  }, []);

  const showUnlock = useCallback(() => {
    setShowDialog(true);
  }, []);

  const handleApiError = useCallback((status: number, body?: string): boolean => {
    if (status === 403 && body && body.includes('E2EE')) {
      setIsE2eeRequired(true);
      setShowDialog(true);
      return true;
    }
    return false;
  }, []);

  const handleUnlocked = useCallback(() => {
    const hash = getStoredKeyHash();
    setKeyHash(hash);
    setIsUnlocked(true);
    setIsE2eeRequired(false);
    setShowDialog(false);
    window.location.reload();
  }, []);

  const handleClose = useCallback(() => {
    setShowDialog(false);
  }, []);

  return (
    <E2eeContext.Provider value={{ isE2eeRequired, isUnlocked, keyHash, showUnlock, handleApiError }}>
      {children}
      {showDialog && <E2eeUnlock onUnlocked={handleUnlocked} onClose={handleClose} />}
    </E2eeContext.Provider>
  );
}
