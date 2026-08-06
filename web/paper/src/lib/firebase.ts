/**
 * Firebase auth for PAPER.
 *
 * Mirrors `web/app/src/lib/firebase.ts` — same env var names, same Google provider
 * setup, same "always fetch a fresh ID token before an API call" rule — trimmed to
 * the one thing this app needs: knowing who is reading, so the backend can build
 * their edition. No messaging, no Apple provider, no analytics.
 *
 * Initialization is lazy and configuration is checked, because an unconfigured
 * deployment must say so plainly rather than fail inside the Firebase SDK.
 */

import { initializeApp, getApps, type FirebaseApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  type Auth,
  type User,
} from 'firebase/auth';

export type { User };

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

/**
 * The four values Firebase Auth genuinely cannot work without. Checked up front so a
 * missing `.env` reads as a setup problem on the page instead of an SDK stack trace.
 */
export const isFirebaseConfigured = Boolean(
  firebaseConfig.apiKey &&
    firebaseConfig.authDomain &&
    firebaseConfig.projectId &&
    firebaseConfig.appId,
);

export const MISSING_CONFIG_MESSAGE =
  'Sign-in is not configured for this deployment. Set the NEXT_PUBLIC_FIREBASE_* values listed in .env.template.';

let cachedAuth: Auth | null = null;

function firebaseAuth(): Auth {
  if (!isFirebaseConfigured) {
    throw new Error(MISSING_CONFIG_MESSAGE);
  }
  if (!cachedAuth) {
    const app: FirebaseApp =
      getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];
    cachedAuth = getAuth(app);
  }
  return cachedAuth;
}

const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: 'select_account' });

/** Sign in with Google. Throws on failure; the caller prints the reason. */
export async function signInWithGoogle(): Promise<User> {
  const result = await signInWithPopup(firebaseAuth(), googleProvider);
  return result.user;
}

export async function signOutUser(): Promise<void> {
  await signOut(firebaseAuth());
}

/**
 * The current reader's ID token. Fetched fresh per request — never cached here —
 * because a stale token is indistinguishable from an unauthenticated one at the API.
 */
export async function getIdToken(): Promise<string | null> {
  const user = firebaseAuth().currentUser;
  if (!user) return null;
  return user.getIdToken();
}

/** Subscribe to auth state. Returns the unsubscribe function. */
export function onAuthStateChange(callback: (user: User | null) => void): () => void {
  return onAuthStateChanged(firebaseAuth(), callback);
}
