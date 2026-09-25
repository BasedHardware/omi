import { createElement } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * `AuthProvider` starts at `loading: true` and only leaves it when the auth
 * subscription reports a state. `ProtectedRoute` renders a full-screen spinner
 * for the whole of `loading`, so a subscription that never reports is a blank
 * app, not a degraded one.
 *
 * That is the shape of a local preview build: `.env.local` carries the
 * `preview` / `preview.local` placeholders `lib/firebase.ts` recognises, no
 * Firebase app is created, and every route — including `/login`, which ships a
 * "Sign-in is not configured in this local preview." message for exactly this
 * case — sits on the spinner.
 */

const PREVIEW_ENV = {
  NEXT_PUBLIC_FIREBASE_API_KEY: 'preview',
  NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: 'preview.local',
  NEXT_PUBLIC_FIREBASE_PROJECT_ID: 'preview',
  NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET: 'preview',
  NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID: 'preview',
  NEXT_PUBLIC_FIREBASE_APP_ID: 'preview',
};

const CONFIGURED_ENV = {
  NEXT_PUBLIC_FIREBASE_API_KEY: 'test-api-key',
  NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: 'test.firebaseapp.com',
  NEXT_PUBLIC_FIREBASE_PROJECT_ID: 'test-project',
  NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET: 'test-project.appspot.com',
  NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID: '1234567890',
  NEXT_PUBLIC_FIREBASE_APP_ID: '1:1234567890:web:abcdef',
};

const firebaseAuth = vi.hoisted(() => ({
  onAuthStateChanged: vi.fn(
    (_auth: unknown, _callback: (user: unknown) => void): (() => void) =>
      () => {},
  ),
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
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
  onAuthStateChanged: firebaseAuth.onAuthStateChanged,
}));

vi.mock('firebase/messaging', () => ({
  getMessaging: vi.fn(),
  getToken: vi.fn(),
  onMessage: vi.fn(),
  isSupported: async () => false,
}));

vi.mock('@/lib/analytics/mixpanel', () => ({
  MixpanelManager: {
    init: vi.fn(),
    identify: vi.fn(),
    track: vi.fn(),
    reset: vi.fn(),
  },
}));

function stubEnvironment(values: Record<string, string>): void {
  for (const [key, value] of Object.entries(values)) vi.stubEnv(key, value);
}

async function renderProvider() {
  const { AuthProvider, useAuth } = await import('../AuthProvider');

  function Probe() {
    const { user, loading } = useAuth();
    return createElement(
      'div',
      { 'data-testid': 'probe' },
      `${loading ? 'loading' : 'settled'}:${user?.uid ?? 'anonymous'}`,
    );
  }

  render(createElement(AuthProvider, null, createElement(Probe)));
  return screen.getByTestId('probe');
}

beforeEach(() => {
  vi.resetModules();
  firebaseAuth.onAuthStateChanged.mockClear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

describe('AuthProvider', () => {
  it('settles as signed out when the preview placeholders leave Firebase unconfigured', async () => {
    stubEnvironment(PREVIEW_ENV);

    const probe = await renderProvider();

    await waitFor(() => expect(probe).toHaveTextContent('settled:anonymous'));
    expect(firebaseAuth.onAuthStateChanged).not.toHaveBeenCalled();
  });

  it('reports the signed-in user when Firebase is configured', async () => {
    stubEnvironment(CONFIGURED_ENV);
    firebaseAuth.onAuthStateChanged.mockImplementation((_auth, callback) => {
      callback({ uid: 'user-1' });
      return () => {};
    });

    const probe = await renderProvider();

    await waitFor(() => expect(probe).toHaveTextContent('settled:user-1'));
    expect(firebaseAuth.onAuthStateChanged).toHaveBeenCalledTimes(1);
  });
});
