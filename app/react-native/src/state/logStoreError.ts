import { useAuthStore } from './authStore';

/**
 * Logs a store load failure, and returns the message for the store's error state.
 *
 * The logging is conditional on purpose. `console.error` in React Native opens
 * LogBox as a blocking full-screen panel, once per store -- so a demo session,
 * which has no token and therefore 401s on every server call, buried the app under
 * four dialogs the moment it launched. The error state is still set either way, so
 * a screen that wants to show "sign in to see this" still can; only the blocking
 * overlay is suppressed.
 */
export function logStoreError(scope: string, err: unknown, fallback = 'Request failed'): string {
  const msg = err instanceof Error ? err.message : fallback;
  if (!useAuthStore.getState().isDemo) {
    console.error(`[${scope}] load failed:`, msg);
  }
  return msg;
}