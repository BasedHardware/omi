'use client';

import { createContext, useContext, useEffect, useState, ReactNode, useRef, useCallback } from 'react';
import { User } from 'firebase/auth';
import {
  onAuthStateChange,
  signInWithGoogle,
  signInWithApple,
  signOutUser,
  getIdToken,
  completeRedirectSignIn,
} from '@/lib/firebase';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithApple: () => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
  // Login panel state
  isLoginPanelOpen: boolean;
  openLoginPanel: () => void;
  closeLoginPanel: () => void;
  /**
   * Why a redirect sign-in came back without a session. Mobile signs in by
   * leaving the page, so this is the only place its failures can be reported.
   */
  redirectSignInError: unknown;
  clearRedirectSignInError: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [isLoginPanelOpen, setIsLoginPanelOpen] = useState(false);
  const [redirectSignInError, setRedirectSignInError] = useState<unknown>(null);
  const previousUserRef = useRef<User | null>(null);

  const openLoginPanel = useCallback(() => setIsLoginPanelOpen(true), []);
  const closeLoginPanel = useCallback(() => setIsLoginPanelOpen(false), []);
  const clearRedirectSignInError = useCallback(() => setRedirectSignInError(null), []);

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

    // A sign-in that left the page through `signInWithRedirect` reports its
    // outcome here, on the way back. It has to run on every route: the provider
    // returns the user to whichever page started the sign-in, and a failure is
    // otherwise indistinguishable from a page that simply has no session.
    void completeRedirectSignIn()
      .then((redirectedUser) => {
        if (redirectedUser) {
          MixpanelManager.track('Sign In Completed', { method: 'redirect' });
        }
      })
      .catch((error) => {
        console.error('Redirect sign-in failed:', error);
        setRedirectSignInError(error);
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
    isLoginPanelOpen,
    openLoginPanel,
    closeLoginPanel,
    redirectSignInError,
    clearRedirectSignInError,
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
