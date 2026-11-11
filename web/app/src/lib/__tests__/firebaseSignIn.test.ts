import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Phones cannot open a popup and complete it without leaving the page, and the
 * sign-in SDK reports that as `auth/popup-closed-by-user` — the message a real
 * user saw after doing nothing wrong. These tests pin the split: a popup on a
 * desktop, a full-page redirect on a phone, and a reader for the result the
 * redirect leaves behind.
 */

const firebase = vi.hoisted(() => ({
  signInWithPopup: vi.fn(async () => ({ user: { uid: 'popup-user' } })),
  signInWithRedirect: vi.fn(async () => {}),
  getRedirectResult: vi.fn(async (): Promise<unknown> => null),
}));

vi.mock('firebase/app', () => ({
  initializeApp: () => ({ name: 'test-app' }),
  getApps: () => [],
}));

vi.mock('firebase/auth', () => ({
  getAuth: () => ({}),
  GoogleAuthProvider: class {
    setCustomParameters() {}
  },
  OAuthProvider: class {
    addScope() {}
  },
  signInWithPopup: firebase.signInWithPopup,
  signInWithRedirect: firebase.signInWithRedirect,
  getRedirectResult: firebase.getRedirectResult,
  signOut: vi.fn(),
  onAuthStateChanged: vi.fn(),
}));

vi.mock('firebase/messaging', () => ({
  getMessaging: vi.fn(),
  getToken: vi.fn(),
  onMessage: vi.fn(),
  isSupported: async () => false,
}));

const CONFIGURED_ENV = {
  NEXT_PUBLIC_FIREBASE_API_KEY: 'test-api-key',
  NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: 'test.firebaseapp.com',
  NEXT_PUBLIC_FIREBASE_PROJECT_ID: 'test-project',
  NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET: 'test-project.appspot.com',
  NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID: '1234567890',
  NEXT_PUBLIC_FIREBASE_APP_ID: '1:1234567890:web:abcdef',
};

const IPHONE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';
const DESKTOP_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

function stubUserAgent(userAgent: string): void {
  Object.defineProperty(window.navigator, 'userAgent', {
    value: userAgent,
    configurable: true,
  });
}

beforeEach(() => {
  vi.resetModules();
  firebase.signInWithPopup.mockClear();
  firebase.signInWithRedirect.mockClear();
  firebase.getRedirectResult.mockReset().mockResolvedValue(null);
  for (const [key, value] of Object.entries(CONFIGURED_ENV)) vi.stubEnv(key, value);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('signInWithGoogle', () => {
  it('redirects instead of opening a popup on a phone', async () => {
    stubUserAgent(IPHONE_UA);

    const { signInWithGoogle } = await import('../firebase');
    await signInWithGoogle();

    expect(firebase.signInWithRedirect).toHaveBeenCalledTimes(1);
    expect(firebase.signInWithPopup).not.toHaveBeenCalled();
  });

  it('keeps the popup on a desktop browser', async () => {
    stubUserAgent(DESKTOP_UA);

    const { signInWithGoogle } = await import('../firebase');
    await signInWithGoogle();

    expect(firebase.signInWithPopup).toHaveBeenCalledTimes(1);
    expect(firebase.signInWithRedirect).not.toHaveBeenCalled();
  });
});

describe('completeRedirectSignIn', () => {
  it('reports the user a redirect came back with', async () => {
    stubUserAgent(IPHONE_UA);
    firebase.getRedirectResult.mockResolvedValueOnce({ user: { uid: 'redirect-user' } });

    const { completeRedirectSignIn } = await import('../firebase');

    await expect(completeRedirectSignIn()).resolves.toEqual({ uid: 'redirect-user' });
  });

  it('resolves with nothing on an ordinary page load', async () => {
    stubUserAgent(DESKTOP_UA);

    const { completeRedirectSignIn } = await import('../firebase');

    await expect(completeRedirectSignIn()).resolves.toBeNull();
  });
});
