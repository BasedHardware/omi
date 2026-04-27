/**
 * Header forwarder for backend-routed API calls.
 *
 * Reads the user's per-account settings (BYOK keys + EU Privacy Mode flag)
 * server-side and assembles the headers that omi backend's M1 dispatcher
 * needs to make the right routing decision:
 *
 * - `Authorization: Bearer <firebase-id-token>` always present so the
 *   backend can resolve the user.
 * - `X-BYOK-<Provider>: <plaintext-key>` for each provider the user has
 *   configured. Decryption happens here (server-side only) — plaintext
 *   never leaves this process and never persists.
 * - `X-Privacy-Mode: on` when the user has EU Privacy Mode enabled.
 *
 * Server-only — must NEVER ship in the browser bundle. Importers should be
 * Server Actions or route handlers.
 *
 * Mirrors the desktop's APIClient header forwarding (see
 * desktop/Desktop/Sources/APIClient.swift on the same branch).
 */

import {
  BYOK_PROVIDERS,
  getBYOKKeyForBackendForwarding,
  getUserSettings,
  type BYOKProvider,
  type UserSettings,
} from '@/src/lib/firestore/user-settings';

const PROVIDER_HEADER: Record<BYOKProvider, string> = {
  openai: 'X-BYOK-OpenAI',
  anthropic: 'X-BYOK-Anthropic',
  gemini: 'X-BYOK-Gemini',
  deepgram: 'X-BYOK-Deepgram',
  regolo: 'X-BYOK-Regolo',
};

export interface ForwarderOptions {
  /** Additional headers the caller wants merged in (e.g. Content-Type). */
  extraHeaders?: Record<string, string>;
}

/**
 * Pure mapping from `(settings, idToken, byokKeyResolver, options)` to a
 * Headers object. Exported for tests so we can exercise the assembly logic
 * without a live Firestore connection or webcrypto-derived keys.
 */
export function buildHeadersFromSettings(
  settings: UserSettings,
  idToken: string,
  /** Synchronous resolver: provider → plaintext key (or null). Used by tests
   *  with stubbed keys; production path uses the async getBYOKKeyForBackendForwarding. */
  resolveByokKey: (provider: BYOKProvider) => string | null,
  options: ForwarderOptions = {},
): Headers {
  if (!idToken) {
    throw new Error('idToken is required for backend header forwarding');
  }

  const headers = new Headers(options.extraHeaders);
  headers.set('Authorization', `Bearer ${idToken}`);

  for (const provider of BYOK_PROVIDERS) {
    if (!settings.byok_keys[provider]) continue;
    const plaintext = resolveByokKey(provider);
    if (plaintext) headers.set(PROVIDER_HEADER[provider], plaintext);
  }

  if (settings.eu_privacy_mode) {
    headers.set('X-Privacy-Mode', 'on');
  }

  return headers;
}

/**
 * Production path: fetch user settings from Firestore, decrypt configured
 * BYOK keys, assemble the Headers object. Caller passes the user's UID and
 * Firebase ID token; the rest is read from `users/{uid}/settings/profile`.
 *
 * The returned Headers object is freshly built per call — callers can
 * mutate it freely (e.g. set Content-Type) without affecting other calls.
 */
export async function buildBackendHeaders(
  uid: string,
  idToken: string,
  options: ForwarderOptions = {},
): Promise<Headers> {
  if (!uid) throw new Error('uid is required');

  const settings = await getUserSettings(uid);

  // Decrypt every configured BYOK key once up-front. We need them sync
  // for buildHeadersFromSettings, so resolve the promises into a map first.
  const plaintextByProvider = new Map<BYOKProvider, string | null>();
  for (const provider of BYOK_PROVIDERS) {
    if (!settings.byok_keys[provider]) {
      plaintextByProvider.set(provider, null);
      continue;
    }
    plaintextByProvider.set(provider, await getBYOKKeyForBackendForwarding(uid, provider));
  }

  return buildHeadersFromSettings(
    settings,
    idToken,
    (provider) => plaintextByProvider.get(provider) ?? null,
    options,
  );
}
