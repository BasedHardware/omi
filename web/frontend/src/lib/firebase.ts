// Import the functions you need from the SDKs you need
import { initializeApp } from 'firebase/app';
import {
  connectAuthEmulator,
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  User,
} from 'firebase/auth';
import { resolveAuthEmulatorUrl } from './firebase-auth-emulator.mjs';

// Firebase configuration
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID,
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Firebase Auth and get a reference to the service
export const auth = getAuth(app);

// Local development only. `resolveAuthEmulatorUrl` refuses production builds and
// non-loopback hosts, so a leaked env var cannot redirect real sign-in.
const authEmulatorUrl = resolveAuthEmulatorUrl({
  NODE_ENV: process.env.NODE_ENV,
  NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST:
    process.env.NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST,
});
if (authEmulatorUrl) {
  connectAuthEmulator(auth, authEmulatorUrl, { disableWarnings: false });
}

// Initialize Google Auth Provider
const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({
  prompt: 'select_account',
});

// Auth functions
export const signInWithGoogle = async (): Promise<User | null> => {
  try {
    console.log('🔑 Initiating Google sign-in...');
    const result = await signInWithPopup(auth, googleProvider);
    console.log('✅ Google sign-in successful:', {
      uid: result.user.uid,
      email: result.user.email,
      displayName: result.user.displayName,
    });
    return result.user;
  } catch (error) {
    if (error instanceof Error) {
      console.error('❌ Google sign-in error:', error.message);
    }
    throw error;
  }
};

export const signOutUser = async (): Promise<void> => {
  try {
    console.log('🚪 Signing out user...');
    await signOut(auth);
    console.log('✅ User signed out successfully');
  } catch (error) {
    if (error instanceof Error) {
      console.error('❌ Sign out error:', error.message);
    }
    throw error;
  }
};

export const onAuthStateChange = (callback: (user: User | null) => void) => {
  return onAuthStateChanged(auth, (user) => {
    if (user) {
      console.log('👤 User authenticated:', {
        uid: user.uid,
        email: user.email,
        displayName: user.displayName,
      });
    } else {
      console.log('🚫 User not authenticated');
    }
    callback(user);
  });
};

export default app;
