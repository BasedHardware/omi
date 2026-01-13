import { initializeApp, getApps } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  OAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  User,
} from 'firebase/auth';
import {
  getMessaging,
  getToken,
  onMessage,
  isSupported,
  Messaging,
  MessagePayload,
} from 'firebase/messaging';

// Firebase configuration from environment variables
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID,
};

// Initialize Firebase (prevent multiple initializations)
const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];

// Initialize Firebase Auth
export const auth = getAuth(app);

// Google Auth Provider
const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({
  prompt: 'select_account',
});

// Apple Auth Provider
const appleProvider = new OAuthProvider('apple.com');
appleProvider.addScope('email');
appleProvider.addScope('name');

/**
 * Sign in with Google
 */
export const signInWithGoogle = async (): Promise<User | null> => {
  try {
    const result = await signInWithPopup(auth, googleProvider);
    return result.user;
  } catch (error) {
    console.error('Google sign-in error:', error);
    throw error;
  }
};

/**
 * Sign in with Apple
 */
export const signInWithApple = async (): Promise<User | null> => {
  try {
    const result = await signInWithPopup(auth, appleProvider);
    return result.user;
  } catch (error) {
    console.error('Apple sign-in error:', error);
    throw error;
  }
};

/**
 * Sign out the current user
 */
export const signOutUser = async (): Promise<void> => {
  try {
    await signOut(auth);
  } catch (error) {
    console.error('Sign out error:', error);
    throw error;
  }
};

/**
 * Get the current user's ID token for API calls
 * Always call this fresh before API requests (don't cache)
 */
export const getIdToken = async (): Promise<string | null> => {
  const user = auth.currentUser;
  if (!user) return null;

  try {
    // Force refresh if token is expired
    const token = await user.getIdToken();
    return token;
  } catch (error) {
    console.error('Get ID token error:', error);
    return null;
  }
};

/**
 * Subscribe to auth state changes
 */
export const onAuthStateChange = (callback: (user: User | null) => void) => {
  return onAuthStateChanged(auth, callback);
};

// ============================================
// Firebase Cloud Messaging (FCM) for Push Notifications
// ============================================

// VAPID key for web push
const VAPID_KEY = process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY;

// Cached messaging instance
let messagingInstance: Messaging | null = null;

/**
 * Check if the browser supports Firebase Cloud Messaging
 */
export const isMessagingSupported = async (): Promise<boolean> => {
  if (typeof window === 'undefined') return false;

  try {
    return await isSupported();
  } catch {
    return false;
  }
};

/**
 * Get the Firebase Messaging instance (lazy initialization)
 * Returns null if messaging is not supported
 */
export const getMessagingInstance = async (): Promise<Messaging | null> => {
  if (typeof window === 'undefined') return null;

  if (messagingInstance) return messagingInstance;

  const supported = await isMessagingSupported();
  if (!supported) {
    console.warn('Firebase Messaging is not supported in this browser');
    return null;
  }

  try {
    messagingInstance = getMessaging(app);
    return messagingInstance;
  } catch (error) {
    console.error('Failed to initialize Firebase Messaging:', error);
    return null;
  }
};

/**
 * Register the service worker for FCM and wait for it to be active
 */
const registerServiceWorker = async (): Promise<ServiceWorkerRegistration | null> => {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
    return null;
  }

  try {
    const registration = await navigator.serviceWorker.register('/firebase-messaging-sw.js');
    console.log('Service Worker registered:', registration);

    // Wait for the service worker to be active
    const installingWorker = registration.installing;
    if (installingWorker) {
      await new Promise<void>((resolve) => {
        const handler = (e: Event) => {
          if ((e.target as ServiceWorker).state === 'activated') {
            installingWorker.removeEventListener('statechange', handler);
            resolve();
          }
        };
        installingWorker.addEventListener('statechange', handler);
      });
    } else {
      const waitingWorker = registration.waiting;
      if (waitingWorker) {
        await new Promise<void>((resolve) => {
          const handler = (e: Event) => {
            if ((e.target as ServiceWorker).state === 'activated') {
              waitingWorker.removeEventListener('statechange', handler);
              resolve();
            }
          };
          waitingWorker.addEventListener('statechange', handler);
        });
      }
    }

    // Also ensure the service worker is ready
    await navigator.serviceWorker.ready;
    console.log('Service Worker is active and ready');

    return registration;
  } catch (error) {
    console.error('Service Worker registration failed:', error);
    return null;
  }
};

/**
 * Request notification permission and get FCM token
 * @returns The FCM token if permission granted, null otherwise
 */
export const requestNotificationPermission = async (): Promise<string | null> => {
  if (typeof window === 'undefined') return null;

  // Check if notifications are supported
  if (!('Notification' in window)) {
    console.warn('This browser does not support notifications');
    return null;
  }

  // Check if service workers are supported
  if (!('serviceWorker' in navigator)) {
    console.warn('Service workers are not supported');
    return null;
  }

  // Register service worker FIRST (before calling getMessaging)
  const swRegistration = await registerServiceWorker();
  if (!swRegistration) return null;

  // Request permission
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    console.log('Notification permission denied');
    return null;
  }

  // Now get messaging instance (after SW is registered)
  const messaging = await getMessagingInstance();
  if (!messaging) return null;

  // Get FCM token
  try {
    const token = await getToken(messaging, {
      vapidKey: VAPID_KEY,
      serviceWorkerRegistration: swRegistration,
    });

    if (token) {
      console.log('FCM Token obtained');
      return token;
    } else {
      console.warn('No FCM token available');
      return null;
    }
  } catch (error) {
    console.error('Failed to get FCM token:', error);
    return null;
  }
};

/**
 * Get the current FCM token without requesting permission
 * Useful for checking if we already have a valid token
 */
export const getCurrentFCMToken = async (): Promise<string | null> => {
  if (typeof window === 'undefined') return null;

  // Check current permission status
  if (Notification.permission !== 'granted') {
    return null;
  }

  // Check if service workers are supported
  if (!('serviceWorker' in navigator)) {
    return null;
  }

  // Register service worker FIRST
  const swRegistration = await registerServiceWorker();
  if (!swRegistration) return null;

  // Then get messaging instance
  const messaging = await getMessagingInstance();
  if (!messaging) return null;

  try {
    const token = await getToken(messaging, {
      vapidKey: VAPID_KEY,
      serviceWorkerRegistration: swRegistration,
    });
    return token || null;
  } catch (error) {
    console.error('Failed to get current FCM token:', error);
    return null;
  }
};

/**
 * Subscribe to foreground messages
 * These are messages received while the app is in focus
 * @param callback Function to call when a message is received
 * @returns Unsubscribe function
 */
export const onForegroundMessage = async (
  callback: (payload: MessagePayload) => void
): Promise<(() => void) | null> => {
  const messaging = await getMessagingInstance();
  if (!messaging) {
    console.warn('[FCM] Cannot subscribe to foreground messages - messaging not available');
    return null;
  }

  console.log('[FCM] Subscribing to foreground messages');
  return onMessage(messaging, (payload) => {
    console.log('[FCM] Foreground message received:', payload);
    callback(payload);
  });
};

/**
 * Get the current notification permission status
 */
export const getNotificationPermission = (): NotificationPermission | 'unsupported' => {
  if (typeof window === 'undefined' || !('Notification' in window)) {
    return 'unsupported';
  }
  return Notification.permission;
};

export default app;
