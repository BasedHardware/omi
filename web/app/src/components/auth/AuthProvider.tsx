'use client';

import { createContext, useContext, useEffect, useState, ReactNode, useRef } from 'react';
import { User } from 'firebase/auth';
import {
  auth,
  onAuthStateChange,
  signInWithGoogle,
  signInWithApple,
  signOutUser,
  getIdToken,
} from '@/lib/firebase';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithApple: () => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const previousUserRef = useRef<User | null>(null);

  useEffect(() => {
    // Initialize Mixpanel
    MixpanelManager.init();

    // Subscribe to auth state changes
    const unsubscribe = onAuthStateChange((user) => {
      setUser(user);
      setLoading(false);

      // Identify user with Mixpanel when authenticated
      if (user && !previousUserRef.current) {
        MixpanelManager.identify(user.uid, {
          name: user.displayName || undefined,
          email: user.email || undefined,
        });
      }

      previousUserRef.current = user;
    });

    return () => unsubscribe();
  }, []);

  const handleSignInWithGoogle = async () => {
    try {
      await signInWithGoogle();
      MixpanelManager.track('Sign In Completed', { method: 'google' });
    } catch (error) {
      console.error('Failed to sign in with Google:', error);
      throw error;
    }
  };

  const handleSignInWithApple = async () => {
    try {
      await signInWithApple();
      MixpanelManager.track('Sign In Completed', { method: 'apple' });
    } catch (error) {
      console.error('Failed to sign in with Apple:', error);
      throw error;
    }
  };

  const handleSignOut = async () => {
    try {
      MixpanelManager.track('Sign Out');
      MixpanelManager.reset();
      await signOutUser();
    } catch (error) {
      console.error('Failed to sign out:', error);
      throw error;
    }
  };

  const handleGetToken = async () => {
    return getIdToken();
  };

  const value: AuthContextType = {
    user,
    loading,
    signInWithGoogle: handleSignInWithGoogle,
    signInWithApple: handleSignInWithApple,
    signOut: handleSignOut,
    getToken: handleGetToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
