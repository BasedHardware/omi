// Import the functions you need from the SDKs you need
import { initializeApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  User,
} from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';

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

// Firestore handle — used by web/frontend/src/lib/firestore/* for the user-
// settings store (M4.1 onward). Same Firebase project as Auth so the security
// rules can pin reads/writes to `request.auth.uid`.
export const db = getFirestore(app);

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
