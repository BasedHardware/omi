import { create } from 'zustand';
import { observeAuth, signOut, signInWithGoogle, signInWithApple } from '@/auth/firebaseAuth';

/**
 * Marks the session created by loginWithoutAccount(). Anything that must not talk
 * to a real account checks for it: a demo session has no token, so a request built
 * from it is unauthenticated and the API answers 401 rather than someone else's
 * data.
 */
export const DEMO_UID = 'local-demo-user';

interface AuthState {
  uid: string | null;
  token: string | null;
  /** True only for a local session with no account behind it. */
  isDemo: boolean;
  loading: boolean;
  error: string | null;
  init: () => () => void;
  loginWithGoogle: () => Promise<void>;
  loginWithApple: () => Promise<void>;
  logout: () => Promise<void>;
  loginWithoutAccount: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  uid: null,
  token: null,
  isDemo: false,
  loading: true,
  error: null,
  init: () => {
    const unsub = observeAuth((uid, token) => {
      set({ uid, token, loading: false, isDemo: false });
    });
    return () => {
      unsub();
    };
  },
  loginWithGoogle: async () => {
    set({ loading: true, error: null });
    try {
      await signInWithGoogle();
    } catch (e: any) {
      console.error('[auth] Google sign-in error:', e);
      set({ error: e?.message ?? 'Google sign-in failed' });
    } finally {
      set({ loading: false });
    }
  },
  loginWithApple: async () => {
    set({ loading: true, error: null });
    try {
      await signInWithApple();
    } catch (e: any) {
      console.error('[auth] Apple sign-in error:', e);
      set({ error: e?.message ?? 'Apple sign-in failed' });
    } finally {
      set({ loading: false });
    }
  },
  /**
   * Dev only. Enters the app with a local session so the tabs and the on-device
   * local brain can be exercised without a real account.
   *
   * No token is set, on purpose. This is a way to reach the UI, not a way to
   * impersonate anyone: any request that needs credentials still fails, which is
   * the honest behaviour for a session that does not exist.
   */
  loginWithoutAccount: () => {
    set({ uid: DEMO_UID, token: null, isDemo: true, loading: false, error: null });
  },
  logout: async () => {
    await signOut();
    set({ uid: null, token: null, isDemo: false });
  },
}));
