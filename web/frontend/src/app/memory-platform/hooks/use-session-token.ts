'use client';

import { useCallback, useEffect, useState } from 'react';
import type { User } from 'firebase/auth';
import { auth, onAuthStateChange } from '@/src/lib/firebase';

export interface SessionState {
  user: User | null;
  loading: boolean;
  /**
   * Returns a fresh Firebase ID token. The token is never written to durable
   * browser storage by this surface.
   *
   * Stable across renders: consumers use it as a `useCallback` dependency and
   * those callbacks as `useEffect` dependencies, so a new identity per render
   * would make every successful load immediately trigger another one.
   */
  getToken: () => Promise<string | null>;
}

export function useSessionToken(): SessionState {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthStateChange((nextUser) => {
      setUser(nextUser);
      setLoading(false);
    });
    return () => unsubscribe();
  }, []);

  const getToken = useCallback(async () => {
    const current = auth.currentUser;
    if (!current) return null;
    return current.getIdToken();
  }, []);

  return { user, loading, getToken };
}
