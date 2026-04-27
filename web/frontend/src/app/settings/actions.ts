'use server';

/**
 * Server Actions exposed to the /settings UI.
 *
 * The UI component (`page.tsx`) is a client component because Firebase Auth
 * state is needed to extract the uid + Firebase ID token. These actions are
 * the server-side bridge that wraps the M4.1 Firestore prefs store + the
 * BYOK validator. Plaintext BYOK keys live only inside these actions and
 * the encryption module — never returned to the client, never logged.
 *
 * Auth: every action takes the Firebase ID token as the first argument and
 * verifies it against Firebase Admin to extract the uid. (For now we trust
 * the client-supplied uid; once Firebase Admin is wired in, swap the
 * `authenticateRequest` stub for a real verification step.)
 */

import {
  BYOK_PROVIDERS,
  setBYOKKey as storeBYOKKey,
  setEuPrivacyMode as storeEuPrivacyMode,
  getUserSettings,
  type BYOKProvider,
} from '@/src/lib/firestore/user-settings';

const PROVIDER_VALIDATION_ENDPOINT: Record<BYOKProvider, string | null> = {
  // Provider-direct probes; same pattern as desktop's BYOKValidator.swift.
  openai: 'https://api.openai.com/v1/models',
  anthropic: 'https://api.anthropic.com/v1/models',
  gemini: 'https://generativelanguage.googleapis.com/v1beta/models',
  deepgram: 'https://api.deepgram.com/v1/projects',
  regolo: 'https://api.regolo.ai/v1/models',
};

export interface SettingsSnapshot {
  eu_privacy_mode: boolean;
  configured_providers: BYOKProvider[];
}

/**
 * Read the user's settings snapshot for display. Never returns plaintext
 * keys — only which providers are configured.
 */
export async function fetchSettingsSnapshot(uid: string): Promise<SettingsSnapshot> {
  if (!uid) throw new Error('uid is required');
  const settings = await getUserSettings(uid);
  return {
    eu_privacy_mode: settings.eu_privacy_mode,
    configured_providers: BYOK_PROVIDERS.filter((p) => settings.byok_keys[p]),
  };
}

export async function saveBYOKKey(
  uid: string,
  provider: BYOKProvider,
  plaintextKey: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  if (!uid) return { ok: false, error: 'uid is required' };
  try {
    await storeBYOKKey(uid, provider, plaintextKey.trim());
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'unknown error' };
  }
}

export async function saveEuPrivacyMode(
  uid: string,
  enabled: boolean,
): Promise<{ ok: true } | { ok: false; error: string }> {
  if (!uid) return { ok: false, error: 'uid is required' };
  try {
    await storeEuPrivacyMode(uid, enabled);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'unknown error' };
  }
}

/**
 * Test a plaintext key against the provider's models endpoint without
 * persisting it. The plaintext is sent server-side to the provider only;
 * we don't store anything from this call. Mirrors desktop's BYOKValidator
 * behavior — see desktop/Desktop/Sources/BYOKValidator.swift.
 *
 * Returns ok=true on 2xx, ok=false with a short error reason otherwise.
 */
export async function testBYOKConnection(
  provider: BYOKProvider,
  plaintextKey: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  if (!plaintextKey || !plaintextKey.trim()) {
    return { ok: false, error: 'Key is empty' };
  }

  const endpoint = PROVIDER_VALIDATION_ENDPOINT[provider];
  if (!endpoint) {
    return { ok: false, error: `No validation endpoint for ${provider}` };
  }

  // Each provider has its own auth header convention. Match the desktop's
  // BYOKValidator pattern: most use Authorization: Bearer; Anthropic uses
  // x-api-key; Gemini puts the key in a query param.
  const trimmed = plaintextKey.trim();
  const init: RequestInit = { method: 'GET', cache: 'no-store' };
  let url = endpoint;

  if (provider === 'anthropic') {
    init.headers = { 'x-api-key': trimmed, 'anthropic-version': '2023-06-01' };
  } else if (provider === 'gemini') {
    url = `${endpoint}?key=${encodeURIComponent(trimmed)}`;
  } else if (provider === 'deepgram') {
    init.headers = { Authorization: `Token ${trimmed}` };
  } else {
    init.headers = { Authorization: `Bearer ${trimmed}` };
  }

  try {
    const res = await fetch(url, init);
    if (res.ok) return { ok: true };
    if (res.status === 401 || res.status === 403) {
      return { ok: false, error: `Rejected (HTTP ${res.status})` };
    }
    return { ok: false, error: `HTTP ${res.status}` };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'network error' };
  }
}
