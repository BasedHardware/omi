import { initializeApp, getApps } from 'firebase/app';
import {
  getAuth,
  signInWithCustomToken,
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
const app =
  typeof window === 'undefined'
    ? null
    : getApps().length === 0
      ? initializeApp(firebaseConfig)
      : getApps()[0];

// Initialize Firebase Auth
export const auth = app ? getAuth(app) : (null as unknown as ReturnType<typeof getAuth>);

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';
const WEB_AUTH_SESSION_KEY = 'omi.web.auth.pending';

type WebAuthSession = {
  state: string;
  codeVerifier: string;
  redirectUri: string;
  destination: string;
};

function randomUrlSafeValue(byteLength: number): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

async function codeChallengeForVerifier(codeVerifier: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(codeVerifier),
  );
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function webAuthRedirectUri(): string {
  return `${window.location.origin}/login`;
}

function safeDestination(destination: string | undefined): string {
  if (destination && destination.startsWith('/') && !destination.startsWith('//')) {
    return destination;
  }
  return '/conversations';
}

async function startWebOAuth(
  provider: 'google' | 'apple',
  destination?: string,
): Promise<void> {
  if (typeof window === 'undefined')
    throw new Error('Web authentication is only available in a browser');

  const codeVerifier = randomUrlSafeValue(64);
  const state = randomUrlSafeValue(32);
  const redirectUri = webAuthRedirectUri();
  const session: WebAuthSession = {
    state,
    codeVerifier,
    redirectUri,
    destination: safeDestination(destination),
  };
  sessionStorage.setItem(WEB_AUTH_SESSION_KEY, JSON.stringify(session));

  const codeChallenge = await codeChallengeForVerifier(codeVerifier);
  const params = new URLSearchParams({
    provider,
    redirect_uri: redirectUri,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });
  window.location.assign(`${API_BASE_URL}/v1/auth/authorize?${params.toString()}`);
}

export async function completeWebOAuth(code: string, state: string): Promise<string> {
  if (typeof window === 'undefined')
    throw new Error('Web authentication is only available in a browser');

  const rawSession = sessionStorage.getItem(WEB_AUTH_SESSION_KEY);
  if (!rawSession) throw new Error('Sign-in session expired. Start again.');

  let session: WebAuthSession;
  try {
    session = JSON.parse(rawSession) as WebAuthSession;
  } catch {
    sessionStorage.removeItem(WEB_AUTH_SESSION_KEY);
    throw new Error('Sign-in session is invalid. Start again.');
  }

  if (session.state !== state || session.redirectUri !== webAuthRedirectUri()) {
    sessionStorage.removeItem(WEB_AUTH_SESSION_KEY);
    throw new Error('Sign-in state did not match. Start again.');
  }

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    redirect_uri: session.redirectUri,
    use_custom_token: 'true',
    code_verifier: session.codeVerifier,
  });
  const response = await fetch('/api/auth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  const payload = (await response.json().catch(() => ({}))) as {
    custom_token?: string;
    detail?: string;
  };
  if (!response.ok || !payload.custom_token) {
    throw new Error(payload.detail || 'Web sign-in could not be completed.');
  }

  await signInWithCustomToken(auth, payload.custom_token);
  sessionStorage.removeItem(WEB_AUTH_SESSION_KEY);
  return session.destination;
}

/**
 * Sign in with Google
 */
// Google Auth Provider
export const signInWithGoogle = async (destination?: string): Promise<void> => {
  await startWebOAuth('google', destination);
};

/**
 * Sign in with Apple
 */
// Apple Auth Provider
export const signInWithApple = async (destination?: string): Promise<void> => {
  await startWebOAuth('apple', destination);
};

/**
 * Sign out the current user
 */
export const signOutUser = async (): Promise<void> => {
  try {
    if (!app) return;
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
  if (!app) return () => {};
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
    if (!app) return null;
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
    const registration = await navigator.serviceWorker.register(
      '/firebase-messaging-sw.js',
    );

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
      return token;
    } else {
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
  callback: (payload: MessagePayload) => void,
): Promise<(() => void) | null> => {
  const messaging = await getMessagingInstance();
  if (!messaging) {
    return null;
  }

  return onMessage(messaging, (payload) => {
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
