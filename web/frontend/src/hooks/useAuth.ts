'use client';

import { useEffect, useState } from 'react';
import { User } from 'firebase/auth';
import { onAuthStateChange, signInWithGoogle, signOutUser } from '../lib/firebase';

interface UseAuthReturn {
  user: User | null;
  loading: boolean;
  signIn: () => Promise<User | null>;
  signOut: () => Promise<void>;
  isAuthenticated: boolean;
  authError: string | null;
}

export const useAuth = (): UseAuthReturn => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    console.log('🔧 Setting up auth state listener...');

    let unsubscribe: (() => void) | null = null;

    try {
      unsubscribe = onAuthStateChange((user: User | null) => {
        setUser(user);
        setLoading(false);
        setAuthError(null); // Clear any previous errors
      });
    } catch (error: any) {
      console.error('❌ Firebase auth initialization failed:', error.message);
      setAuthError(error.message);
      setLoading(false);
      // Don't crash the app - just set user to null and continue
      setUser(null);
    }

    return () => {
      console.log('🧹 Cleaning up auth state listener...');
      try {
        if (unsubscribe) {
          unsubscribe();
        }
      } catch (error: any) {
        console.error('❌ Error cleaning up auth listener:', error.message);
      }
    };
  }, []);

  const signIn = async (): Promise<User | null> => {
    try {
      setLoading(true);
      setAuthError(null);
      const user = await signInWithGoogle();
      return user;
    } catch (error: any) {
      console.error('❌ Sign in failed:', error);
      setAuthError(error.message || 'Sign in failed');
      return null; // Don't throw - return null instead
    } finally {
      setLoading(false);
    }
  };

  const signOut = async (): Promise<void> => {
    try {
      setLoading(true);
      setAuthError(null);
      await signOutUser();
    } catch (error: any) {
      console.error('❌ Sign out failed:', error);
      setAuthError(error.message || 'Sign out failed');
      // Don't throw - just log the error
    } finally {
      setLoading(false);
    }
  };

  return {
    user,
    loading,
    signIn,
    signOut,
    isAuthenticated: !!user,
    authError,
  };
};
