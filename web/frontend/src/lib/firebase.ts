// Import the functions you need from the SDKs you need
import { initializeApp, getApps, FirebaseApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  User,
  Auth,
} from 'firebase/auth';

// Check if Firebase is configured
const isFirebaseConfigured = (): boolean => {
  return !!(
    process.env.NEXT_PUBLIC_FIREBASE_API_KEY &&
    process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID
  );
};

// Firebase configuration
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || 'demo-api-key',
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || 'demo-project.firebaseapp.com',
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || 'demo-project',
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || 'demo-project.appspot.com',
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || '123456789',
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID || '1:123456789:web:abcdef',
  measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID,
};

// Initialize Firebase only if configured, otherwise create a mock app
let app: FirebaseApp | null = null;
let auth: Auth | null = null;

if (isFirebaseConfigured()) {
  try {
    // Initialize Firebase only if not already initialized
    if (getApps().length === 0) {
      app = initializeApp(firebaseConfig);
      auth = getAuth(app);
      console.log('✅ Firebase initialized successfully');
    } else {
      app = getApps()[0];
      auth = getAuth(app);
    }
  } catch (error) {
    console.warn('⚠️  Firebase initialization failed, continuing without Firebase:', error);
    app = null;
    auth = null;
  }
} else {
  console.warn('⚠️  Firebase not configured - running in demo mode without authentication');
  // Create a mock auth object that we can use
  auth = null;
}

// Initialize Google Auth Provider (only if auth is available)
let googleProvider: GoogleAuthProvider | null = null;
if (auth) {
  googleProvider = new GoogleAuthProvider();
  googleProvider.setCustomParameters({
    prompt: 'select_account',
  });
}

// Auth functions with fallbacks
export const signInWithGoogle = async (): Promise<User | null> => {
  if (!auth || !googleProvider) {
    console.warn('⚠️  Firebase not configured - sign in disabled');
    return null;
  }

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
  if (!auth) {
    console.warn('⚠️  Firebase not configured - sign out disabled');
    return;
  }

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
  if (!auth) {
    console.warn('⚠️  Firebase not configured - no auth state changes');
    // Call callback immediately with null user
    callback(null);
    // Return a no-op unsubscribe function
    return () => { };
  }

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

// Export auth - will be null if Firebase is not configured
export { auth };
export default app;
